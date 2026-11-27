"""审计只读。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import current_user
from db import connect

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(limit: int = 100, user=Depends(current_user)):
    limit = max(1, min(limit, 500))
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
