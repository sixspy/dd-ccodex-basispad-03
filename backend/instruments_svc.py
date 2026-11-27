"""永续标的台账。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from models import INSTRUMENT_KINDS
from policies import assert_writable_role

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


class InstrumentBody(BaseModel):
    symbol: str
    title: str
    kind: str = "perp"
    quote_ccy: str = "USDT"
    base_ccy: str = "BTC"
    tick_size: float = 0.1
    lot_size: float = 0.001
    funding_interval_h: int = 8
    max_leverage: float = 20
    status: str = "active"
    note: str = ""


class InstrumentPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    max_leverage: float | None = None
    funding_interval_h: int | None = None
    note: str | None = None


@router.get("")
def list_instruments(status: str | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM instruments"
    args: list = []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY id"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.get("/{iid}")
def get_instrument(iid: int, user=Depends(current_user)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM instruments WHERE id=?", (iid,)).fetchone()
        if not row:
            raise HTTPException(404, "标的不存在")
        return dict(row)


@router.post("")
def create_instrument(body: InstrumentBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    if body.kind not in INSTRUMENT_KINDS:
        raise HTTPException(400, f"kind 须为 {INSTRUMENT_KINDS}")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM instruments WHERE symbol=?", (body.symbol,)).fetchone():
            raise HTTPException(409, "symbol 已存在")
        cur = conn.execute(
            "INSERT INTO instruments(symbol,title,kind,quote_ccy,base_ccy,tick_size,lot_size,"
            "funding_interval_h,max_leverage,status,note) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                body.symbol,
                body.title,
                body.kind,
                body.quote_ccy,
                body.base_ccy,
                body.tick_size,
                body.lot_size,
                body.funding_interval_h,
                body.max_leverage,
                body.status,
                body.note,
            ),
        )
        iid = cur.lastrowid
        audit(conn, user["username"], "create", "instrument", iid, body.symbol)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM instruments WHERE id=?", (iid,)).fetchone())


@router.patch("/{iid}")
def patch_instrument(iid: int, body: InstrumentPatch, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        row = conn.execute("SELECT * FROM instruments WHERE id=?", (iid,)).fetchone()
        if not row:
            raise HTTPException(404, "标的不存在")
        data = dict(row)
        for k, v in body.model_dump(exclude_none=True).items():
            data[k] = v
        conn.execute(
            "UPDATE instruments SET title=?,status=?,max_leverage=?,funding_interval_h=?,note=? WHERE id=?",
            (data["title"], data["status"], data["max_leverage"], data["funding_interval_h"], data["note"], iid),
        )
        audit(conn, user["username"], "patch", "instrument", iid, data["status"])
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM instruments WHERE id=?", (iid,)).fetchone())
