"""费率丙轨 · 强平成交与仓位边须同步记账（失败测甲）。

起点事故：`queued` 强平单点执行后，保证金页显示 liquidated，
但成交回报里没有 `source='liquidation'` 行，仓位边仍挂旧名义。

甲口径（正式路径）：执行强平必须在同一事务内
  1) 写正式强平成交（fills.source='liquidation'，note 回指 LIQ 编码）；
  2) 回写仓位（qty / avg_entry / realized_pnl）；
  3) 队列状态 queued -> executed；
  4) 保证金占用按新仓位重算后落库。
任一步失败或缺成交，整笔零增回滚：队列仍 queued、成交零增、仓位零改、保证金零改。
"""
from __future__ import annotations

import sqlite3

import pytest

LIQ_ID = 1
SLEEVE_ID = 2
INSTRUMENT_ID = 3


def _snapshot(client, h) -> dict:
    liq = [r for r in client.get("/api/margin/liquidations", headers=h).json() if r["id"] == LIQ_ID][0]
    sleeve = client.get(f"/api/sleeves/{SLEEVE_ID}", headers=h).json()
    margin = [m for m in client.get("/api/margin/states", headers=h).json() if m["sleeve_id"] == SLEEVE_ID][0]
    fills = [f for f in client.get("/api/matcher/fills", headers=h).json() if f["sleeve_id"] == SLEEVE_ID]
    liq_fills = [f for f in fills if f["source"] == "liquidation" and f["note"] == liq["code"]]
    pos = [p for p in sleeve["positions"] if p["instrument_id"] == INSTRUMENT_ID]
    return {
        "liq": liq,
        "fills": fills,
        "liq_fills": liq_fills,
        "position": pos[0] if pos else None,
        "margin": margin,
    }


def _assert_zero_delta(before: dict, after: dict) -> None:
    """失败路径断言：正式区零增、仓位零改、保证金零改、队列仍 queued。"""
    assert after["liq"]["status"] == "queued"
    assert after["liq"]["executed_at"] is None
    assert len(after["liq_fills"]) == len(before["liq_fills"]) == 0
    assert len(after["fills"]) == len(before["fills"])
    assert after["margin"]["status"] == before["margin"]["status"]
    assert after["margin"]["used_margin"] == pytest.approx(before["margin"]["used_margin"])
    if before["position"] is not None:
        assert after["position"]["qty"] == pytest.approx(before["position"]["qty"])
        assert after["position"]["avg_entry"] == pytest.approx(before["position"]["avg_entry"])
        assert after["position"]["realized_pnl"] == pytest.approx(before["position"]["realized_pnl"])


def test_execute_writes_liquidation_fill_in_same_txn(client, login):
    """执行后必有 liquidation 成交，且与仓位/队列同一事务落地。"""
    h = login()
    before = _snapshot(client, h)
    assert before["liq"]["status"] == "queued"
    assert before["position"] is not None and abs(before["position"]["qty"]) > 0
    old_qty = before["position"]["qty"]
    liq_qty = min(before["liq"]["qty"], abs(old_qty))

    r = client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fill_code"].startswith("FIL-")
    assert body["fill_code"].startswith("FIL-")

    after = _snapshot(client, h)
    # 强平成交行存在且恰好一笔
    assert len(after["liq_fills"]) == 1
    fill = after["liq_fills"][0]
    assert fill["sleeve_id"] == SLEEVE_ID
    assert fill["instrument_id"] == INSTRUMENT_ID
    assert fill["source"] == "liquidation"
    assert fill["qty"] == pytest.approx(liq_qty)
    assert fill["price"] == pytest.approx(before["liq"]["trigger_mark"])
    assert fill["note"] == before["liq"]["code"]
    assert fill["ticket_id"] is None

    # 队列正式升为 executed 且带成交号
    assert after["liq"]["status"] == "executed"
    assert after["liq"]["executed_at"] is not None
    assert after["liq"]["fill_code"] == fill["code"]
    assert after["liq"]["remaining_qty"] == pytest.approx(0.0, abs=1e-9)

    # 仓位边同步：qty 减到位，realized_pnl 变化与成交方向一致
    assert after["position"]["qty"] == pytest.approx(old_qty - liq_qty)
    assert after["position"]["realized_pnl"] != pytest.approx(before["position"]["realized_pnl"])

    # 保证金同源：占用按新仓位重算，不再挂旧名义
    assert after["margin"]["status"] == "liquidated"
    assert after["margin"]["used_margin"] == pytest.approx(0.0, abs=1e-9)
    assert after["margin"]["used_margin"] < before["margin"]["used_margin"] or before["margin"]["used_margin"] == 0


def test_execute_is_idempotent_rejects_second_time(client, login):
    """已执行强平单不可二次执行，且不产生第二笔强平成交。"""
    h = login()
    assert client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h).status_code == 200
    after_first = _snapshot(client, h)
    r2 = client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h)
    assert r2.status_code == 409
    after_second = _snapshot(client, h)
    assert len(after_second["liq_fills"]) == len(after_first["liq_fills"]) == 1
    assert after_second["position"]["qty"] == pytest.approx(after_first["position"]["qty"])


def test_missing_fill_leaves_zero_delta(client, login, db_conn):
    """失败测甲：成交写口被破坏 -> 执行失败，正式区零增（禁止无成交改状态）。"""
    h = login()
    before = _snapshot(client, h)
    # 制造写口故障：fills 表上挂一个拒绝插入的触发器（仅模拟写失败，不改业务代码）
    db_conn.execute(
        "CREATE TRIGGER boom_fill BEFORE INSERT ON fills "
        "BEGIN SELECT RAISE(ABORT, 'fill write failed'); END"
    )
    db_conn.commit()
    try:
        r = client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h)
        assert r.status_code >= 500, f"期望失败，实际 {r.status_code} {r.text}"
    finally:
        db_conn.execute("DROP TRIGGER IF EXISTS boom_fill")
        db_conn.commit()
    after = _snapshot(client, h)
    _assert_zero_delta(before, after)


def test_fill_write_failure_does_not_touch_margin_status(client, login, db_conn):
    """失败测甲补充：不得出现「无强平成交却把保证金标成 liquidated」的假绿。"""
    h = login()
    before = _snapshot(client, h)
    db_conn.execute(
        "CREATE TRIGGER boom_pos BEFORE UPDATE ON positions "
        "BEGIN SELECT RAISE(ABORT, 'position write failed'); END"
    )
    db_conn.commit()
    try:
        r = client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h)
        assert r.status_code >= 500, f"期望失败，实际 {r.status_code} {r.text}"
    finally:
        db_conn.execute("DROP TRIGGER IF EXISTS boom_pos")
        db_conn.commit()
    after = _snapshot(client, h)
    _assert_zero_delta(before, after)
    assert after["margin"]["status"] != "liquidated"


def test_liq_without_position_rolls_back(client, login):
    """仓位边已空时执行须拒绝，且不写成交、不改状态。"""
    h = login()
    # 另入队一张无仓强平不可能（enqueue 已拦），这里直接构造仓位清零后的执行
    assert client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h).status_code == 200
    liq2 = client.post(
        "/api/margin/liquidations/enqueue",
        headers=h,
        json={"sleeve_id": SLEEVE_ID, "instrument_id": INSTRUMENT_ID},
    )
    # 仓位已平，enqueue 应拒绝
    assert liq2.status_code == 409
    with db_conn_guard() as conn:
        fills = conn.execute("SELECT COUNT(*) c FROM fills WHERE source='liquidation'").fetchone()["c"]
    assert fills == 1


class db_conn_guard:
    def __enter__(self):
        import db as dbmod

        self.conn = dbmod.connect()
        return self.conn

    def __exit__(self, *exc):
        self.conn.close()
        return False
