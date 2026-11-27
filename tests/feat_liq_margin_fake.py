"""费率丙轨 · 保证金页禁止把影子强平当已清算（失败测乙）。

事故：正式强平仍 queued、成交回报无 liquidation 行，
保证金页却把「影子强平/旧状态」显示成 liquidated（假绿）。

乙口径（影子草案）在本案被明确拒绝：不得先落影子强平草案再升正；
正式成交与仓位在升正前必须零改。保证金页只认正式凭据：
  - liquidation_queue.status='executed' 且关联成交号存在；
  - fills 中同 sleeve/instrument 有 source='liquidation' 的同额行；
  - positions.qty 已完成扣减。
任一缺失则页面不得显示 liquidated，且对账接口必须报违规。
"""
from __future__ import annotations

import pytest

SLEEVE_ID = 2
INSTRUMENT_ID = 3
LIQ_ID = 1


def _margin_state(client, h) -> dict:
    return [m for m in client.get("/api/margin/states", headers=h).json() if m["sleeve_id"] == SLEEVE_ID][0]


def _recon(client, h) -> dict:
    r = client.get("/api/audit/liq_recon", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_queued_liq_never_shows_liquidated(client, login):
    h = login()
    state = _margin_state(client, h)
    assert state["status"] != "liquidated"
    recon = _recon(client, h)
    assert recon["ok"] is True
    assert recon["violations"] == []
    assert recon["queued"] >= 1


def test_fake_green_state_flagged_and_not_displayed(client, login, db_conn):
    """构造影子假绿：队列仍 queued，保证金行被写成 liquidated。"""
    h = login()
    db_conn.execute(
        "UPDATE margin_states SET status='liquidated' WHERE sleeve_id=?", (SLEEVE_ID,)
    )
    db_conn.commit()

    state = _margin_state(client, h)
    assert state["status"] != "liquidated", "queued 强平下保证金页不得显示已清算"
    assert state["status_stored"] == "liquidated"
    assert state["status_source"] == "reconciled"

    recon = _recon(client, h)
    assert recon["ok"] is False
    kinds = {v["kind"] for v in recon["violations"]}
    assert "liquidated_without_fill" in kinds
    bad = [v for v in recon["violations"] if v["kind"] == "liquidated_without_fill"][0]
    assert bad["sleeve_id"] == SLEEVE_ID
    assert bad["liq_id"] == LIQ_ID


def test_shadow_draft_status_is_not_official(client, login, db_conn):
    """乙路径痕迹不得冒用正式状态：影子态只允许落在非正式字段。"""
    h = login()
    # 影子草案若存在，绝不能把队列写成 executed 或写正式成交
    db_conn.execute(
        "UPDATE liquidation_queue SET status='shadow_draft', executed_at=NULL WHERE id=?", (LIQ_ID,)
    )
    db_conn.commit()
    recon = _recon(client, h)
    assert recon["ok"] is False
    kinds = {v["kind"] for v in recon["violations"]}
    assert "unexpected_liq_status" in kinds
    state = _margin_state(client, h)
    assert state["status"] != "liquidated"
    fills = client.get("/api/matcher/fills", headers=h).json()
    assert not [f for f in fills if f["source"] == "liquidation"]


def test_executed_without_fill_is_violation(client, login, db_conn):
    """队列被打成 executed 但无强平成交 -> 假绿，必须报违规且页面不显示已清算。"""
    h = login()
    db_conn.execute(
        "UPDATE liquidation_queue SET status='executed', executed_at=1, fill_code=NULL WHERE id=?",
        (LIQ_ID,),
    )
    db_conn.commit()
    recon = _recon(client, h)
    assert recon["ok"] is False
    kinds = {v["kind"] for v in recon["violations"]}
    assert "executed_without_fill" in kinds
    state = _margin_state(client, h)
    assert state["status"] != "liquidated"


def test_after_real_execution_page_shows_liquidated(client, login):
    """正式执行后（成交+仓位齐套）页面才允许显示 liquidated。"""
    h = login()
    assert client.post(f"/api/margin/liquidations/{LIQ_ID}/execute", headers=h).status_code == 200
    state = _margin_state(client, h)
    assert state["status"] == "liquidated"
    assert state["status_source"] == "official"
    recon = _recon(client, h)
    assert recon["ok"] is True, recon
    assert recon["violations"] == []
    assert recon["executed"] == 1


def test_write_green_and_recon_green_are_separate_services(client, login):
    """写口绿与对账绿必须分属异服务：执行接口与联查接口不是同一路由/模块。"""
    from audit_svc import liq_recon
    from margin_svc import execute_liq

    assert execute_liq is not liq_recon
    assert execute_liq.__module__ == "margin_svc"
    assert liq_recon.__module__ == "audit_svc"

    h = login()
    # 对账接口只读：调用前后正式区计数不变
    before = len(client.get("/api/matcher/fills", headers=h).json())
    assert client.get("/api/audit/liq_recon", headers=h).status_code == 200
    assert len(client.get("/api/matcher/fills", headers=h).json()) == before
    liq = [r for r in client.get("/api/margin/liquidations", headers=h).json() if r["id"] == LIQ_ID][0]
    assert liq["status"] == "queued"
