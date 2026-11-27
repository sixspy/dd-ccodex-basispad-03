"""总览看板。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import current_user
from db import connect
from policies import unrealized_pnl

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(user=Depends(current_user)):
    with connect() as conn:
        instruments = conn.execute("SELECT COUNT(*) c FROM instruments WHERE status='active'").fetchone()["c"]
        sleeves = conn.execute("SELECT COUNT(*) c FROM sleeves WHERE status='active'").fetchone()["c"]
        open_tickets = conn.execute(
            "SELECT COUNT(*) c FROM tickets WHERE status IN ('open','partial')"
        ).fetchone()["c"]
        fills = conn.execute("SELECT COUNT(*) c FROM fills").fetchone()["c"]
        queued_liq = conn.execute(
            "SELECT COUNT(*) c FROM liquidation_queue WHERE status='queued'"
        ).fetchone()["c"]
        draft_funding = conn.execute(
            "SELECT COUNT(*) c FROM funding_snapshots WHERE status='draft'"
        ).fetchone()["c"]
        locked_settle = conn.execute(
            "SELECT COUNT(*) c FROM settle_batches WHERE status='locked'"
        ).fetchone()["c"]
        official_settle = conn.execute(
            "SELECT COUNT(*) c FROM settle_batches WHERE official=1"
        ).fetchone()["c"]
        wallet_bal = conn.execute("SELECT COALESCE(SUM(balance),0) s FROM wallets").fetchone()["s"]
        upnl = 0.0
        for p in conn.execute("SELECT * FROM positions WHERE qty != 0").fetchall():
            mark = conn.execute(
                "SELECT mark FROM mark_prices WHERE instrument_id=?", (p["instrument_id"],)
            ).fetchone()
            m = mark["mark"] if mark else p["avg_entry"]
            upnl += unrealized_pnl(p["qty"], p["avg_entry"], m)
        return {
            "instruments": instruments,
            "active_sleeves": sleeves,
            "open_tickets": open_tickets,
            "fills": fills,
            "queued_liquidations": queued_liq,
            "draft_funding": draft_funding,
            "locked_settle_batches": locked_settle,
            "official_settle_batches": official_settle,
            "wallet_balance_sum": wallet_bal,
            "aggregate_upnl": upnl,
        }
