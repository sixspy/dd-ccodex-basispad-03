"""纸面撮合与成交回写。"""
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
    round_px,
    write_margin_state,
)

router = APIRouter(prefix="/api/matcher", tags=["matcher"])


class MatchBody(BaseModel):
    ticket_id: int
    fill_price: float | None = None
    fill_qty: float | None = None
    fee_bps: float = 2.0


def _next_fill_code(conn) -> str:
    n = conn.execute("SELECT COUNT(*) c FROM fills").fetchone()["c"] + 1
    return f"FIL-{n:05d}"


def _refresh_margin(conn, sleeve_id: int, leverage: float = 1.0) -> None:
    """成交后保证金与仓位同源：统一走 write_margin_state，禁止各写各的。"""
    write_margin_state(conn, sleeve_id, max(leverage, 1.0))


@router.post("/match")
def match_ticket(body: MatchBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    resource = f"ticket:{body.ticket_id}"
    with connect() as conn:
        acquire_lock(conn, resource, user["username"], "match")
        try:
            ticket = conn.execute("SELECT * FROM tickets WHERE id=?", (body.ticket_id,)).fetchone()
            if not ticket:
                raise HTTPException(404, "委托不存在")
            if ticket["status"] not in ("open", "partial"):
                raise HTTPException(409, "委托不可撮合")
            sleeve = conn.execute("SELECT * FROM sleeves WHERE id=?", (ticket["sleeve_id"],)).fetchone()
            if sleeve["status"] != "active":
                raise HTTPException(409, "策略簿已冻结")
            # 结算封批锁定期间禁止撮合
            locked = conn.execute(
                "SELECT 1 FROM settle_batches WHERE status='locked' AND official=0"
            ).fetchone()
            if locked:
                raise HTTPException(409, "存在锁定中的结算批次，禁止撮合")
            inst = conn.execute(
                "SELECT * FROM instruments WHERE id=?", (ticket["instrument_id"],)
            ).fetchone()
            mark = conn.execute(
                "SELECT * FROM mark_prices WHERE instrument_id=?", (ticket["instrument_id"],)
            ).fetchone()
            remain = ticket["qty"] - ticket["filled_qty"]
            fill_qty = body.fill_qty if body.fill_qty is not None else remain
            if fill_qty <= 0 or fill_qty > remain + 1e-12:
                raise HTTPException(400, "成交数量非法")
            if ticket["order_type"] == "market":
                px = body.fill_price if body.fill_price is not None else (mark["mark"] if mark else 0)
            else:
                px = body.fill_price if body.fill_price is not None else ticket["price"]
                if ticket["side"] == "buy" and px > ticket["price"] + 1e-12:
                    raise HTTPException(409, "买单成交价高于限价")
                if ticket["side"] == "sell" and px < ticket["price"] - 1e-12:
                    raise HTTPException(409, "卖单成交价低于限价")
            px = round_px(px, inst["tick_size"])
            fee = abs(px * fill_qty) * body.fee_bps / 10000.0
            code = _next_fill_code(conn)
            now = time.time()
            cur = conn.execute(
                "INSERT INTO fills(code,ticket_id,sleeve_id,instrument_id,side,price,qty,fee,source,created_at,note)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    code,
                    ticket["id"],
                    ticket["sleeve_id"],
                    ticket["instrument_id"],
                    ticket["side"],
                    px,
                    fill_qty,
                    fee,
                    "matcher",
                    now,
                    "",
                ),
            )
            fill_id = cur.lastrowid
            new_filled = ticket["filled_qty"] + fill_qty
            status = "filled" if new_filled + 1e-12 >= ticket["qty"] else "partial"
            conn.execute(
                "UPDATE tickets SET filled_qty=?, status=? WHERE id=?",
                (new_filled, status, ticket["id"]),
            )
            pos = conn.execute(
                "SELECT * FROM positions WHERE sleeve_id=? AND instrument_id=?",
                (ticket["sleeve_id"], ticket["instrument_id"]),
            ).fetchone()
            old_qty = pos["qty"] if pos else 0.0
            old_avg = pos["avg_entry"] if pos else 0.0
            old_rpnl = pos["realized_pnl"] if pos else 0.0
            new_qty, new_avg, realized = apply_fill_to_position(
                old_qty, old_avg, ticket["side"], fill_qty, px
            )
            if pos:
                conn.execute(
                    "UPDATE positions SET qty=?, avg_entry=?, realized_pnl=?, updated_at=? WHERE id=?",
                    (new_qty, new_avg, old_rpnl + realized, now, pos["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO positions(sleeve_id,instrument_id,qty,avg_entry,realized_pnl,updated_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (ticket["sleeve_id"], ticket["instrument_id"], new_qty, new_avg, realized, now),
                )
            _refresh_margin(conn, ticket["sleeve_id"], ticket["leverage"])
            audit(conn, user["username"], "match", "fill", fill_id, code)
            conn.commit()
            return {
                "fill": row_to_dict(conn.execute("SELECT * FROM fills WHERE id=?", (fill_id,)).fetchone()),
                "ticket_status": status,
            }
        finally:
            release_lock(conn, resource, user["username"])
            conn.commit()


@router.get("/fills")
def list_fills(sleeve_id: int | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM fills WHERE 1=1"
    args: list = []
    if sleeve_id:
        sql += " AND sleeve_id=?"
        args.append(sleeve_id)
    sql += " ORDER BY id DESC LIMIT 200"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
