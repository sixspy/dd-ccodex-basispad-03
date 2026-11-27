"""结算封批。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from locks import acquire_lock, release_lock
from policies import assert_writable_role, settle_batch_code, unrealized_pnl

router = APIRouter(prefix="/api/settle", tags=["settle"])


class BatchBody(BaseModel):
    title: str
    note: str = ""


@router.get("/batches")
def list_batches(status: str | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM settle_batches"
    args: list = []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.get("/batches/{bid}")
def get_batch(bid: int, user=Depends(current_user)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM settle_batches WHERE id=?", (bid,)).fetchone()
        if not row:
            raise HTTPException(404, "批次不存在")
        items = [dict(r) for r in conn.execute("SELECT * FROM settle_items WHERE batch_id=?", (bid,)).fetchall()]
        return {**dict(row), "items": items}


@router.post("/batches")
def create_batch(body: BatchBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM settle_batches").fetchone()["c"] + 1
        code = settle_batch_code(n)
        now = time.time()
        cur = conn.execute(
            "INSERT INTO settle_batches(code,title,status,official,version,funding_count,mtm_total,created_by,created_at,locked_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (code, body.title, "draft", 0, 1, 0, 0, user["username"], now, None, body.note),
        )
        bid = cur.lastrowid
        # 预览条目
        funding_count = 0
        mtm_total = 0.0
        for p in conn.execute("SELECT * FROM positions").fetchall():
            mark = conn.execute(
                "SELECT mark FROM mark_prices WHERE instrument_id=?", (p["instrument_id"],)
            ).fetchone()
            m = mark["mark"] if mark else p["avg_entry"]
            upnl = unrealized_pnl(p["qty"], p["avg_entry"], m)
            fund = conn.execute(
                "SELECT COALESCE(SUM(payment),0) s FROM funding_ledgers WHERE sleeve_id=? AND instrument_id=? AND status='accrued'",
                (p["sleeve_id"], p["instrument_id"]),
            ).fetchone()["s"]
            if fund:
                funding_count += 1
            mtm_total += upnl
            conn.execute(
                "INSERT INTO settle_items(batch_id,sleeve_id,instrument_id,funding_payment,mtm_pnl,note)"
                " VALUES(?,?,?,?,?,?)",
                (bid, p["sleeve_id"], p["instrument_id"], fund, upnl, ""),
            )
        conn.execute(
            "UPDATE settle_batches SET funding_count=?, mtm_total=? WHERE id=?",
            (funding_count, mtm_total, bid),
        )
        audit(conn, user["username"], "create", "settle_batch", bid, code)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM settle_batches WHERE id=?", (bid,)).fetchone())


@router.post("/batches/{bid}/lock")
def lock_batch(bid: int, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    resource = f"settle:{bid}"
    with connect() as conn:
        acquire_lock(conn, resource, user["username"], "lock")
        try:
            row = conn.execute("SELECT * FROM settle_batches WHERE id=?", (bid,)).fetchone()
            if not row:
                raise HTTPException(404, "批次不存在")
            if row["status"] != "draft":
                raise HTTPException(409, "仅 draft 可锁定")
            other = conn.execute(
                "SELECT 1 FROM settle_batches WHERE status='locked' AND id!=?", (bid,)
            ).fetchone()
            if other:
                raise HTTPException(409, "已有其它锁定批次")
            now = time.time()
            conn.execute(
                "UPDATE settle_batches SET status='locked', locked_at=? WHERE id=?",
                (now, bid),
            )
            audit(conn, user["username"], "lock", "settle_batch", bid, row["code"])
            conn.commit()
            return {"ok": True, "status": "locked"}
        finally:
            release_lock(conn, resource, user["username"])
            conn.commit()


@router.post("/batches/{bid}/promote")
def promote_batch(bid: int, user=Depends(require_roles("admin"))):
    """正式升正：同事务写 official；影子升正由题面另实现。"""
    assert_writable_role(user["role"])
    resource = f"settle:{bid}"
    with connect() as conn:
        acquire_lock(conn, resource, user["username"], "promote")
        try:
            row = conn.execute("SELECT * FROM settle_batches WHERE id=?", (bid,)).fetchone()
            if not row:
                raise HTTPException(404, "批次不存在")
            if row["status"] != "locked":
                raise HTTPException(409, "仅 locked 可升正")
            # 旧官方降版
            conn.execute(
                "UPDATE settle_batches SET official=0 WHERE official=1"
            )
            conn.execute(
                "UPDATE settle_batches SET status='official', official=1, version=version+1 WHERE id=?",
                (bid,),
            )
            conn.execute(
                "UPDATE funding_ledgers SET status='settled' WHERE status='accrued'"
            )
            audit(conn, user["username"], "promote", "settle_batch", bid, row["code"])
            conn.commit()
            return {"ok": True, "status": "official", "official": 1}
        finally:
            release_lock(conn, resource, user["username"])
            conn.commit()


@router.post("/batches/{bid}/void")
def void_batch(bid: int, user=Depends(require_roles("admin"))):
    with connect() as conn:
        row = conn.execute("SELECT * FROM settle_batches WHERE id=?", (bid,)).fetchone()
        if not row:
            raise HTTPException(404, "批次不存在")
        if row["official"] == 1:
            raise HTTPException(409, "官方批次不可直接作废")
        conn.execute("UPDATE settle_batches SET status='void' WHERE id=?", (bid,))
        audit(conn, user["username"], "void", "settle_batch", bid, row["code"])
        conn.commit()
        return {"ok": True}
