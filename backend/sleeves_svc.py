"""策略纸面簿。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from models import SLEEVE_STATUSES
from policies import assert_writable_role

router = APIRouter(prefix="/api/sleeves", tags=["sleeves"])


class SleeveBody(BaseModel):
    code: str
    title: str
    owner: str
    base_equity: float = 100000
    max_gross_exposure: float = 500000
    status: str = "active"
    note: str = ""


class SleevePatch(BaseModel):
    title: str | None = None
    status: str | None = None
    max_gross_exposure: float | None = None
    note: str | None = None


@router.get("")
def list_sleeves(status: str | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM sleeves"
    args: list = []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY id"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.get("/{sid}")
def get_sleeve(sid: int, user=Depends(current_user)):
    with connect() as conn:
        row = conn.execute("SELECT * FROM sleeves WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "策略簿不存在")
        positions = [
            dict(r)
            for r in conn.execute("SELECT * FROM positions WHERE sleeve_id=?", (sid,)).fetchall()
        ]
        margin = row_to_dict(
            conn.execute("SELECT * FROM margin_states WHERE sleeve_id=?", (sid,)).fetchone()
        )
        return {**dict(row), "positions": positions, "margin": margin}


@router.post("")
def create_sleeve(body: SleeveBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    if body.status not in SLEEVE_STATUSES:
        raise HTTPException(400, "非法状态")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM sleeves WHERE code=?", (body.code,)).fetchone():
            raise HTTPException(409, "code 已存在")
        now = time.time()
        cur = conn.execute(
            "INSERT INTO sleeves(code,title,owner,status,base_equity,max_gross_exposure,created_at,note)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (
                body.code,
                body.title,
                body.owner,
                body.status,
                body.base_equity,
                body.max_gross_exposure,
                now,
                body.note,
            ),
        )
        sid = cur.lastrowid
        conn.execute(
            "INSERT INTO margin_states(sleeve_id,equity,used_margin,available,status,liq_price_hint,updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (sid, body.base_equity, 0, body.base_equity, "ok", None, now),
        )
        audit(conn, user["username"], "create", "sleeve", sid, body.code)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM sleeves WHERE id=?", (sid,)).fetchone())


@router.patch("/{sid}")
def patch_sleeve(sid: int, body: SleevePatch, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        row = conn.execute("SELECT * FROM sleeves WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "策略簿不存在")
        data = dict(row)
        for k, v in body.model_dump(exclude_none=True).items():
            data[k] = v
        if data["status"] not in SLEEVE_STATUSES:
            raise HTTPException(400, "非法状态")
        conn.execute(
            "UPDATE sleeves SET title=?,status=?,max_gross_exposure=?,note=? WHERE id=?",
            (data["title"], data["status"], data["max_gross_exposure"], data["note"], sid),
        )
        audit(conn, user["username"], "patch", "sleeve", sid, data["status"])
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM sleeves WHERE id=?", (sid,)).fetchone())


@router.post("/{sid}/freeze")
def freeze_sleeve(sid: int, user=Depends(require_roles("admin"))):
    with connect() as conn:
        row = conn.execute("SELECT * FROM sleeves WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "策略簿不存在")
        conn.execute("UPDATE sleeves SET status='frozen' WHERE id=?", (sid,))
        audit(conn, user["username"], "freeze", "sleeve", sid, row["code"])
        conn.commit()
        return {"ok": True, "status": "frozen"}
