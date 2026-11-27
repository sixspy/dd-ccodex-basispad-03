"""委托单。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from models import ORDER_TYPES, SIDES, TICKET_STATUSES
from policies import assert_writable_role, notional, round_px, round_qty

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


class TicketBody(BaseModel):
    code: str
    sleeve_id: int
    instrument_id: int
    side: str
    order_type: str = "limit"
    price: float | None = None
    qty: float
    leverage: float = 1
    note: str = ""


@router.get("")
def list_tickets(status: str | None = None, sleeve_id: int | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM tickets WHERE 1=1"
    args: list = []
    if status:
        sql += " AND status=?"
        args.append(status)
    if sleeve_id:
        sql += " AND sleeve_id=?"
        args.append(sleeve_id)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.get("/{tid}")
def get_ticket(tid: int, user=Depends(current_user)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not row:
            raise HTTPException(404, "委托不存在")
        fills = [dict(r) for r in conn.execute("SELECT * FROM fills WHERE ticket_id=?", (tid,)).fetchall()]
        return {**dict(row), "fills": fills}


@router.post("")
def create_ticket(body: TicketBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    if body.side not in SIDES:
        raise HTTPException(400, "side 非法")
    if body.order_type not in ORDER_TYPES:
        raise HTTPException(400, "order_type 非法")
    with connect() as conn:
        sleeve = conn.execute("SELECT * FROM sleeves WHERE id=?", (body.sleeve_id,)).fetchone()
        if not sleeve:
            raise HTTPException(404, "策略簿不存在")
        if sleeve["status"] != "active":
            raise HTTPException(409, "策略簿非 active，禁止下单")
        inst = conn.execute("SELECT * FROM instruments WHERE id=?", (body.instrument_id,)).fetchone()
        if not inst or inst["status"] != "active":
            raise HTTPException(404, "标的不可用")
        if body.leverage > inst["max_leverage"]:
            raise HTTPException(400, "杠杆超限")
        qty = round_qty(body.qty, inst["lot_size"])
        if qty <= 0:
            raise HTTPException(400, "数量无效")
        price = body.price
        if body.order_type != "market":
            if price is None:
                raise HTTPException(400, "限价单须给 price")
            price = round_px(price, inst["tick_size"])
        mark = conn.execute(
            "SELECT mark FROM mark_prices WHERE instrument_id=?", (body.instrument_id,)
        ).fetchone()
        ref = price if price is not None else (mark["mark"] if mark else 0)
        lim = conn.execute(
            "SELECT * FROM risk_limits WHERE sleeve_id=? AND (instrument_id IS NULL OR instrument_id=?)",
            (body.sleeve_id, body.instrument_id),
        ).fetchone()
        if lim and notional(ref, qty) > lim["max_order_notional"]:
            raise HTTPException(409, "超过单笔名义限额")
        if conn.execute("SELECT 1 FROM tickets WHERE code=?", (body.code,)).fetchone():
            raise HTTPException(409, "code 已存在")
        now = time.time()
        cur = conn.execute(
            "INSERT INTO tickets(code,sleeve_id,instrument_id,side,order_type,price,qty,filled_qty,"
            "status,leverage,created_by,created_at,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                body.code,
                body.sleeve_id,
                body.instrument_id,
                body.side,
                body.order_type,
                price,
                qty,
                0,
                "open",
                body.leverage,
                user["username"],
                now,
                body.note,
            ),
        )
        tid = cur.lastrowid
        audit(conn, user["username"], "create", "ticket", tid, body.code)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone())


@router.post("/{tid}/cancel")
def cancel_ticket(tid: int, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if not row:
            raise HTTPException(404, "委托不存在")
        if row["status"] not in ("open", "partial"):
            raise HTTPException(409, "当前状态不可撤")
        conn.execute("UPDATE tickets SET status='cancelled' WHERE id=?", (tid,))
        audit(conn, user["username"], "cancel", "ticket", tid, row["code"])
        conn.commit()
        return {"ok": True, "status": "cancelled"}
