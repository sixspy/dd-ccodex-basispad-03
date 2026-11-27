"""写路径资源锁。

锁表是「抢占」而非「提示」：抢占动作本身单独提交，
使其它会话在业务事务提交前即可看见持有者，避免双写同一资源。
"""
from __future__ import annotations

import sqlite3
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


def _now() -> float:
    return time.time()


def try_acquire_lock(
    conn, resource: str, holder: str, reason: str = "", ttl_sec: int = 120
) -> tuple[bool, str | None]:
    """原子抢占资源锁。

    返回 (是否抢到, 现行持有者)。抢锁在独立事务内提交，失败不抛异常，
    由调用方决定是否记争用痕（审计）。
    """
    now = _now()
    # 调用方可能已开启事务；先收敛到自动提交，保证抢锁结果立即可见。
    if conn.in_transaction:
        conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM write_locks WHERE expires_at < ?", (now,))
        row = conn.execute("SELECT * FROM write_locks WHERE resource=?", (resource,)).fetchone()
        if row and row["holder"] != holder:
            conn.rollback()
            return False, row["holder"]
        if row:
            # 同一持有者重入：仅续期
            conn.execute(
                "UPDATE write_locks SET reason=?, expires_at=? WHERE resource=?",
                (reason or row["reason"], now + ttl_sec, resource),
            )
        else:
            conn.execute(
                "INSERT INTO write_locks(resource,holder,reason,expires_at) VALUES(?,?,?,?)",
                (resource, holder, reason or "", now + ttl_sec),
            )
        conn.commit()
        return True, None
    except sqlite3.IntegrityError:
        conn.rollback()
        row = conn.execute("SELECT * FROM write_locks WHERE resource=?", (resource,)).fetchone()
        return False, (row["holder"] if row else "unknown")
    except Exception:
        conn.rollback()
        raise


def acquire_lock(conn, resource: str, holder: str, reason: str = "", ttl_sec: int = 120) -> None:
    ok, current = try_acquire_lock(conn, resource, holder, reason, ttl_sec)
    if not ok:
        raise HTTPException(409, f"资源锁定中: {resource} by {current}")


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
