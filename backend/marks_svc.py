"""标记价与基差。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from policies import assert_writable_role, unrealized_pnl

router = APIRouter(prefix="/api/marks", tags=["marks"])


class MarkBody(BaseModel):
    instrument_id: int
    mark: float
    index_price: float
    status: str = "live"


@router.get("")
def list_marks(user=Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT m.*, i.symbol FROM mark_prices m JOIN instruments i ON i.id=m.instrument_id ORDER BY m.instrument_id"
        ).fetchall()
        return [dict(r) for r in rows]


@router.post("/upsert")
def upsert_mark(body: MarkBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        inst = conn.execute("SELECT * FROM instruments WHERE id=?", (body.instrument_id,)).fetchone()
        if not inst:
            raise HTTPException(404, "标的不存在")
        # 结算锁定时禁止改标记价
        if conn.execute("SELECT 1 FROM settle_batches WHERE status='locked'").fetchone():
            raise HTTPException(409, "结算批次锁定中，禁止改标记价")
        basis = 0.0
        if body.index_price:
            basis = (body.mark - body.index_price) / body.index_price * 10000.0
        now = time.time()
        conn.execute(
            "INSERT INTO mark_prices(instrument_id,mark,index_price,basis_bps,status,as_of)"
            " VALUES(?,?,?,?,?,?) ON CONFLICT(instrument_id) DO UPDATE SET"
            " mark=excluded.mark, index_price=excluded.index_price, basis_bps=excluded.basis_bps,"
            " status=excluded.status, as_of=excluded.as_of",
            (body.instrument_id, body.mark, body.index_price, basis, body.status, now),
        )
        audit(conn, user["username"], "upsert", "mark", body.instrument_id, f"mark={body.mark}")
        conn.commit()
        return row_to_dict(
            conn.execute("SELECT * FROM mark_prices WHERE instrument_id=?", (body.instrument_id,)).fetchone()
        )


@router.get("/mtm")
def mtm_report(user=Depends(current_user)):
    with connect() as conn:
        out = []
        for p in conn.execute("SELECT * FROM positions WHERE qty != 0").fetchall():
            mark = conn.execute(
                "SELECT mark FROM mark_prices WHERE instrument_id=?", (p["instrument_id"],)
            ).fetchone()
            m = mark["mark"] if mark else p["avg_entry"]
            out.append(
                {
                    "sleeve_id": p["sleeve_id"],
                    "instrument_id": p["instrument_id"],
                    "qty": p["qty"],
                    "avg_entry": p["avg_entry"],
                    "mark": m,
                    "upnl": unrealized_pnl(p["qty"], p["avg_entry"], m),
                }
            )
        return out


@router.post("/{instrument_id}/freeze")
def freeze_mark(instrument_id: int, user=Depends(require_roles("admin"))):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM mark_prices WHERE instrument_id=?", (instrument_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "无标记价")
        conn.execute(
            "UPDATE mark_prices SET status='frozen' WHERE instrument_id=?", (instrument_id,)
        )
        audit(conn, user["username"], "freeze", "mark", instrument_id, "frozen")
        conn.commit()
        return {"ok": True, "status": "frozen"}
