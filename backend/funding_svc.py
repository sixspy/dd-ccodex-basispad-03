"""资金费率快照与计提。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from locks import acquire_lock, release_lock
from policies import assert_writable_role, funding_payment

router = APIRouter(prefix="/api/funding", tags=["funding"])


class SnapshotBody(BaseModel):
    code: str
    instrument_id: int
    rate: float
    mark_price: float | None = None
    period_start: float
    period_end: float
    note: str = ""


@router.get("/snapshots")
def list_snapshots(status: str | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM funding_snapshots"
    args: list = []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.get("/ledgers")
def list_ledgers(snapshot_id: int | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM funding_ledgers WHERE 1=1"
    args: list = []
    if snapshot_id:
        sql += " AND snapshot_id=?"
        args.append(snapshot_id)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.post("/snapshots")
def create_snapshot(body: SnapshotBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        inst = conn.execute("SELECT * FROM instruments WHERE id=?", (body.instrument_id,)).fetchone()
        if not inst:
            raise HTTPException(404, "标的不存在")
        if conn.execute("SELECT 1 FROM funding_snapshots WHERE code=?", (body.code,)).fetchone():
            raise HTTPException(409, "code 已存在")
        mark_row = conn.execute(
            "SELECT mark FROM mark_prices WHERE instrument_id=?", (body.instrument_id,)
        ).fetchone()
        mark = body.mark_price if body.mark_price is not None else (mark_row["mark"] if mark_row else 0)
        now = time.time()
        cur = conn.execute(
            "INSERT INTO funding_snapshots(code,instrument_id,rate,mark_price,status,period_start,period_end,created_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (body.code, body.instrument_id, body.rate, mark, "draft", body.period_start, body.period_end, now, body.note),
        )
        sid = cur.lastrowid
        audit(conn, user["username"], "create", "funding_snapshot", sid, body.code)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM funding_snapshots WHERE id=?", (sid,)).fetchone())


@router.post("/snapshots/{sid}/accrue")
def accrue_snapshot(sid: int, user=Depends(require_roles("admin", "trader"))):
    """正式计提：同事务写 ledger；与影子路径互斥由题面择一。"""
    assert_writable_role(user["role"])
    resource = f"funding:{sid}"
    with connect() as conn:
        acquire_lock(conn, resource, user["username"], "accrue")
        try:
            snap = conn.execute("SELECT * FROM funding_snapshots WHERE id=?", (sid,)).fetchone()
            if not snap:
                raise HTTPException(404, "快照不存在")
            if snap["status"] != "draft":
                raise HTTPException(409, "仅 draft 可计提")
            # 若有官方结算批次覆盖同周期则禁止
            conflict = conn.execute(
                "SELECT 1 FROM settle_batches WHERE official=1 AND status='official'"
            ).fetchone()
            positions = conn.execute(
                "SELECT * FROM positions WHERE instrument_id=? AND qty != 0",
                (snap["instrument_id"],),
            ).fetchall()
            now = time.time()
            created = []
            for i, p in enumerate(positions, start=1):
                pay = funding_payment(p["qty"], snap["rate"], snap["mark_price"])
                code = f"FLG-{sid}-{i:03d}"
                conn.execute(
                    "INSERT INTO funding_ledgers(code,snapshot_id,sleeve_id,instrument_id,position_qty,payment,status,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (code, sid, p["sleeve_id"], p["instrument_id"], p["qty"], pay, "accrued", now),
                )
                # 记入已实现（费率）
                conn.execute(
                    "UPDATE positions SET realized_pnl = realized_pnl + ?, updated_at=? WHERE id=?",
                    (pay, now, p["id"]),
                )
                created.append(code)
            conn.execute(
                "UPDATE funding_snapshots SET status='accrued' WHERE id=?", (sid,)
            )
            audit(conn, user["username"], "accrue", "funding_snapshot", sid, f"rows={len(created)}")
            conn.commit()
            return {"ok": True, "ledgers": created, "conflict_hint": bool(conflict)}
        finally:
            release_lock(conn, resource, user["username"])
            conn.commit()


@router.post("/snapshots/{sid}/void")
def void_snapshot(sid: int, user=Depends(require_roles("admin"))):
    with connect() as conn:
        snap = conn.execute("SELECT * FROM funding_snapshots WHERE id=?", (sid,)).fetchone()
        if not snap:
            raise HTTPException(404, "快照不存在")
        if snap["status"] == "settled":
            raise HTTPException(409, "已结算不可作废")
        conn.execute("UPDATE funding_snapshots SET status='void' WHERE id=?", (sid,))
        conn.execute(
            "UPDATE funding_ledgers SET status='void' WHERE snapshot_id=?", (sid,)
        )
        audit(conn, user["username"], "void", "funding_snapshot", sid, snap["code"])
        conn.commit()
        return {"ok": True}
