"""费率丙轨 · 两名操作者争用「强平执行互斥」（争用失败测）。

要求：
  - 同一 LIQ 单同一时刻只允许一个会话执行；
  - 败方零正式改：不写强平成交、不改仓位、不改保证金、不改队列；
  - 败方只留争用痕：audit_logs 中 action='execute_contended'，detail 含双方/资源；
  - 锁在业务事务提交前即可被他人看见（否则双成）；
  - 结束后 write_locks 不残留。
"""
from __future__ import annotations

import threading

import pytest

LIQ_ID = 1
SLEEVE_ID = 2
INSTRUMENT_ID = 3


def _liq_fills(client, h):
    return [f for f in client.get("/api/matcher/fills", headers=h).json() if f["source"] == "liquidation"]


def _contended_traces(client, h):
    rows = client.get("/api/audit?limit=500", headers=h).json()
    return [r for r in rows if r["action"] == "execute_contended" and r["entity"] == "liquidation"]


def _seed_round(db_conn):
    """复位到「LIQ-0001 queued + 满仓」现场，重复压锁。"""
    db_conn.execute("DELETE FROM fills WHERE source='liquidation'")
    db_conn.execute("DELETE FROM write_locks")
    db_conn.execute(
        "UPDATE positions SET qty=50, avg_entry=145, realized_pnl=120 WHERE sleeve_id=? AND instrument_id=?",
        (SLEEVE_ID, INSTRUMENT_ID),
    )
    db_conn.execute(
        "UPDATE liquidation_queue SET status='queued', executed_at=NULL, fill_code=NULL, remaining_qty=NULL WHERE id=?",
        (LIQ_ID,),
    )
    db_conn.execute(
        "UPDATE margin_states SET status='liquidating' WHERE sleeve_id=?", (SLEEVE_ID,)
    )
    db_conn.commit()


def race_liq_execute(client, sessions: list[dict], lid: int = LIQ_ID) -> dict[str, int]:
    """并发双请求压「强平执行互斥」：两会话同时点火，返回各自状态码。"""
    barrier = threading.Barrier(len(sessions))
    results: dict[str, int] = {}

    def fire(tag, headers):
        barrier.wait()
        r = client.post(f"/api/margin/liquidations/{lid}/execute", headers=headers)
        results[tag] = r.status_code

    threads = [
        threading.Thread(target=fire, args=(tag, headers)) for tag, headers in sessions
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_two_operators_race_only_one_wins(client, login, db_conn):
    h = login("trader", "trader123")
    h2 = login("admin", "admin123")
    for round_no in range(5):
        _seed_round(db_conn)
        results = race_liq_execute(client, [("trader", h), ("admin", h2)])

        codes = sorted(results.values())
        assert codes == [200, 409], f"第 {round_no} 轮期望一成一败，实际 {results}"

        # 只有一笔正式强平成交
        fills = _liq_fills(client, h)
        assert len(fills) == 1, f"第 {round_no} 轮双成：{fills}"
        # 仓位只被扣一次
        pos = [
            p
            for p in client.get(f"/api/sleeves/{SLEEVE_ID}", headers=h).json()["positions"]
            if p["instrument_id"] == INSTRUMENT_ID
        ][0]
        assert pos["qty"] == pytest.approx(0.0)
        # 队列只被改一次且带成交号
        liq = [r for r in client.get("/api/margin/liquidations", headers=h).json() if r["id"] == LIQ_ID][0]
        assert liq["status"] == "executed"
        assert liq["fill_code"] == fills[0]["code"]
        # 败方零正式改，只留争用痕
        traces = _contended_traces(client, h)
        assert len(traces) == round_no + 1, f"第 {round_no} 轮争用痕数 {len(traces)}"
        assert LIQ_ID == liq["id"]
        # 锁不残留
        assert client.get("/api/locks", headers=h).json() == []


def test_loser_does_not_touch_official_tables(client, login, db_conn):
    """锁被他人持有时执行：409 + 零正式改 + 争用痕。"""
    h = login("trader", "trader123")
    h_admin = login("admin", "admin123")
    _seed_round(db_conn)
    # admin 先占锁（已提交，跨连接可见）
    r = client.post("/api/locks/acquire", headers=h_admin, json={"resource": f"liq:{LIQ_ID}", "reason": "manual"})
    assert r.status_code == 200
    before_fills = len(_liq_fills(client, h))
    before_pos = [
        p
        for p in client.get(f"/api/sleeves/{SLEEVE_ID}", headers=h).json()["positions"]
        if p["instrument_id"] == INSTRUMENT_ID
    ][0]
    before_margin = [
        m for m in client.get("/api/margin/states", headers=h).json() if m["sleeve_id"] == SLEEVE_ID
    ][0]

    r = client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h)
    assert r.status_code == 409
    liq = [x for x in client.get("/api/margin/liquidations", headers=h).json() if x["id"] == LIQ_ID][0]
    assert liq["status"] == "queued"
    assert len(_liq_fills(client, h)) == before_fills
    pos = [
        p
        for p in client.get(f"/api/sleeves/{SLEEVE_ID}", headers=h).json()["positions"]
        if p["instrument_id"] == INSTRUMENT_ID
    ][0]
    assert pos["qty"] == pytest.approx(before_pos["qty"])
    margin = [
        m for m in client.get("/api/margin/states", headers=h).json() if m["sleeve_id"] == SLEEVE_ID
    ][0]
    assert margin["status"] == before_margin["status"]
    assert margin["used_margin"] == pytest.approx(before_margin["used_margin"])
    traces = _contended_traces(client, h)
    assert len(traces) == 1
    assert "trader" in traces[0]["detail"]
    assert "held_by=admin" in traces[0]["detail"]
    assert f"liq:{LIQ_ID}" in traces[0]["detail"]

    # 释放后可由原操作者完成
    assert (
        client.post(
            "/api/locks/release", headers=h_admin, json={"resource": f"liq:{LIQ_ID}", "reason": "done"}
        ).status_code
        == 200
    )
    res = client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h)
    assert res.status_code == 200, res.text
    assert client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h).status_code == 409
    assert len(_liq_fills(client, h)) == before_fills + 1
