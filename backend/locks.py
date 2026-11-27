"""写路径资源锁。"""
from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user
from db import connect

router = APIRouter(prefix="/api/locks", tags=["locks"])


class LockBody(BaseModel):
    resource: str
    reason: str = ""
    ttl_sec: int = 120


def acquire_lock(conn, resource: str, holder: str, reason: str = "", ttl_sec: int = 120) -> None:
    now = time.time()
    conn.execute("DELETE FROM write_locks WHERE expires_at < ?", (now,))
    row = conn.execute("SELECT * FROM write_locks WHERE resource=?", (resource,)).fetchone()
    if row and row["holder"] != holder and row["expires_at"] > now:
        raise HTTPException(409, f"资源锁定中: {resource} by {row['holder']}")
    conn.execute("DELETE FROM write_locks WHERE resource=?", (resource,))
    conn.execute(
        "INSERT INTO write_locks(resource,holder,reason,expires_at) VALUES(?,?,?,?)",
        (resource, holder, reason, now + ttl_sec),
    )


def release_lock(conn, resource: str, holder: str) -> None:
    conn.execute("DELETE FROM write_locks WHERE resource=? AND holder=?", (resource, holder))


@router.get("")
def list_locks(user=Depends(current_user)):
    with connect() as conn:
        rows = conn.execute("SELECT * FROM write_locks ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@router.post("/acquire")
def api_acquire(body: LockBody, user=Depends(current_user)):
    with connect() as conn:
        acquire_lock(conn, body.resource, user["username"], body.reason, body.ttl_sec)
        conn.commit()
    return {"ok": True, "resource": body.resource, "holder": user["username"]}


@router.post("/release")
def api_release(body: LockBody, user=Depends(current_user)):
    with connect() as conn:
        release_lock(conn, body.resource, user["username"])
        conn.commit()
    return {"ok": True}
