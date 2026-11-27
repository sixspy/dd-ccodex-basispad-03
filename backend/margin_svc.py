"""保证金与强平队列。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from locks import acquire_lock, release_lock
from policies import (
    apply_fill_to_position,
    assert_writable_role,
    available_equity,
    liq_code,
    should_liquidate,
    used_margin,
)

router = APIRouter(prefix="/api/margin", tags=["margin"])


class EnqueueLiqBody(BaseModel):
    sleeve_id: int
    instrument_id: int
    qty: float | None = None
    note: str = ""


@router.get("/states")
def list_states(user=Depends(current_user)):
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM margin_states ORDER BY sleeve_id").fetchall()]


@router.post("/recompute/{sleeve_id}")
def recompute(sleeve_id: int, user=Depends(require_roles("admin", "trader"))):
    with connect() as conn:
        sleeve = conn.execute("SELECT * FROM sleeves WHERE id=?", (sleeve_id,)).fetchone()
        if not sleeve:
            raise HTTPException(404, "策略簿不存在")
        positions = conn.execute("SELECT * FROM positions WHERE sleeve_id=?", (sleeve_id,)).fetchall()
        used = 0.0
        upnl = 0.0
        realized = 0.0
        for p in positions:
            mark_row = conn.execute(
                "SELECT mark FROM mark_prices WHERE instrument_id=?", (p["instrument_id"],)
            ).fetchone()
            mark = mark_row["mark"] if mark_row else p["avg_entry"]
            used += used_margin(p["qty"], mark, 5.0)
            upnl += p["qty"] * (mark - p["avg_entry"])
            realized += p["realized_pnl"]
        equity = sleeve["base_equity"] + realized + upnl
        avail = available_equity(equity, used)
        status = "ok"
        if should_liquidate(equity, used):
            status = "liquidating"
        elif avail < 0:
            status = "call"
        elif avail < equity * 0.2:
            status = "warn"
        conn.execute(
            "INSERT INTO margin_states(sleeve_id,equity,used_margin,available,status,liq_price_hint,updated_at)"
            " VALUES(?,?,?,?,?,?,?) ON CONFLICT(sleeve_id) DO UPDATE SET"
            " equity=excluded.equity, used_margin=excluded.used_margin, available=excluded.available,"
            " status=excluded.status, updated_at=excluded.updated_at",
            (sleeve_id, equity, used, avail, status, None, time.time()),
        )
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM margin_states WHERE sleeve_id=?", (sleeve_id,)).fetchone())


@router.get("/liquidations")
def list_liqs(status: str | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM liquidation_queue"
    args: list = []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.post("/liquidations/enqueue")
def enqueue_liq(body: EnqueueLiqBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        pos = conn.execute(
            "SELECT * FROM positions WHERE sleeve_id=? AND instrument_id=?",
            (body.sleeve_id, body.instrument_id),
        ).fetchone()
        if not pos or abs(pos["qty"]) < 1e-12:
            raise HTTPException(409, "无仓可强平")
        mark = conn.execute(
            "SELECT mark FROM mark_prices WHERE instrument_id=?", (body.instrument_id,)
        ).fetchone()
        if not mark:
            raise HTTPException(409, "缺标记价")
        qty = body.qty if body.qty is not None else abs(pos["qty"])
        n = conn.execute("SELECT COUNT(*) c FROM liquidation_queue").fetchone()["c"] + 1
        code = liq_code(n)
        now = time.time()
        cur = conn.execute(
            "INSERT INTO liquidation_queue(code,sleeve_id,instrument_id,qty,trigger_mark,status,created_at,executed_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (code, body.sleeve_id, body.instrument_id, qty, mark["mark"], "queued", now, None, body.note),
        )
        lid = cur.lastrowid
        conn.execute(
            "UPDATE margin_states SET status='liquidating', updated_at=? WHERE sleeve_id=?",
            (now, body.sleeve_id),
        )
        audit(conn, user["username"], "enqueue", "liquidation", lid, code)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM liquidation_queue WHERE id=?", (lid,)).fetchone())


@router.post("/liquidations/{lid}/execute")
def execute_liq(lid: int, user=Depends(require_roles("admin", "trader"))):
    """正式强平路径：同事务写成交；影子路径由题面另实现。"""
    assert_writable_role(user["role"])
    resource = f"liq:{lid}"
    with connect() as conn:
        acquire_lock(conn, resource, user["username"], "execute_liq")
        try:
            item = conn.execute("SELECT * FROM liquidation_queue WHERE id=?", (lid,)).fetchone()
            if not item:
                raise HTTPException(404, "强平单不存在")
            if item["status"] != "queued":
                raise HTTPException(409, "状态不可执行")
            if conn.execute("SELECT 1 FROM settle_batches WHERE status='locked'").fetchone():
                raise HTTPException(409, "结算锁定中禁止强平")
            pos = conn.execute(
                "SELECT * FROM positions WHERE sleeve_id=? AND instrument_id=?",
                (item["sleeve_id"], item["instrument_id"]),
            ).fetchone()
            if not pos:
                raise HTTPException(409, "仓位已空")
            side = "sell" if pos["qty"] > 0 else "buy"
            px = item["trigger_mark"]
            qty = min(item["qty"], abs(pos["qty"]))
            now = time.time()
            n = conn.execute("SELECT COUNT(*) c FROM fills").fetchone()["c"] + 1
            fcode = f"FIL-{n:05d}"
            conn.execute(
                "INSERT INTO fills(code,ticket_id,sleeve_id,instrument_id,side,price,qty,fee,source,created_at,note)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (fcode, None, item["sleeve_id"], item["instrument_id"], side, px, qty, 0, "liquidation", now, item["code"]),
            )
            new_qty, new_avg, realized = apply_fill_to_position(pos["qty"], pos["avg_entry"], side, qty, px)
            conn.execute(
                "UPDATE positions SET qty=?, avg_entry=?, realized_pnl=?, updated_at=? WHERE id=?",
                (new_qty, new_avg, pos["realized_pnl"] + realized, now, pos["id"]),
            )
            conn.execute(
                "UPDATE liquidation_queue SET status='executed', executed_at=? WHERE id=?",
                (now, lid),
            )
            conn.execute(
                "UPDATE margin_states SET status=?, updated_at=? WHERE sleeve_id=?",
                ("liquidated" if abs(new_qty) < 1e-12 else "call", now, item["sleeve_id"]),
            )
            audit(conn, user["username"], "execute", "liquidation", lid, fcode)
            conn.commit()
            return {"ok": True, "fill_code": fcode, "remaining_qty": new_qty}
        finally:
            release_lock(conn, resource, user["username"])
            conn.commit()
