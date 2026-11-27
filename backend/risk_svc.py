"""风控限额与双人审批。"""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from models import RISK_ACTIONS
from policies import assert_writable_role

router = APIRouter(prefix="/api/risk", tags=["risk"])


class LimitBody(BaseModel):
    sleeve_id: int
    instrument_id: int | None = None
    max_position: float
    max_order_notional: float


class RiskReqBody(BaseModel):
    code: str
    sleeve_id: int
    action: str
    payload: dict = {}


@router.get("/limits")
def list_limits(user=Depends(current_user)):
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM risk_limits ORDER BY id").fetchall()]


@router.post("/limits")
def upsert_limit(body: LimitBody, user=Depends(require_roles("admin"))):
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM risk_limits WHERE sleeve_id=? AND IFNULL(instrument_id,-1)=IFNULL(?, -1)",
            (body.sleeve_id, body.instrument_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE risk_limits SET max_position=?, max_order_notional=?, status='active' WHERE id=?",
                (body.max_position, body.max_order_notional, existing["id"]),
            )
            lid = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO risk_limits(sleeve_id,instrument_id,max_position,max_order_notional,status)"
                " VALUES(?,?,?,?,?)",
                (body.sleeve_id, body.instrument_id, body.max_position, body.max_order_notional, "active"),
            )
            lid = cur.lastrowid
        audit(conn, user["username"], "upsert", "risk_limit", lid, f"sleeve={body.sleeve_id}")
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM risk_limits WHERE id=?", (lid,)).fetchone())


@router.get("/requests")
def list_requests(status: str | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM risk_requests"
    args: list = []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        rows = []
        for r in conn.execute(sql, args).fetchall():
            d = dict(r)
            d["payload"] = json.loads(d.pop("payload_json") or "{}")
            rows.append(d)
        return rows


@router.post("/requests")
def create_request(body: RiskReqBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    if body.action not in RISK_ACTIONS:
        raise HTTPException(400, f"action 须为 {RISK_ACTIONS}")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM risk_requests WHERE code=?", (body.code,)).fetchone():
            raise HTTPException(409, "code 已存在")
        now = time.time()
        cur = conn.execute(
            "INSERT INTO risk_requests(code,sleeve_id,action,payload_json,status,requested_by,approved_by,created_at,decided_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (
                body.code,
                body.sleeve_id,
                body.action,
                json.dumps(body.payload, ensure_ascii=False),
                "pending",
                user["username"],
                None,
                now,
                None,
            ),
        )
        rid = cur.lastrowid
        audit(conn, user["username"], "create", "risk_request", rid, body.code)
        conn.commit()
        return {"id": rid, "status": "pending"}


@router.post("/requests/{rid}/approve")
def approve_request(rid: int, user=Depends(require_roles("admin"))):
    with connect() as conn:
        row = conn.execute("SELECT * FROM risk_requests WHERE id=?", (rid,)).fetchone()
        if not row:
            raise HTTPException(404, "申请不存在")
        if row["status"] != "pending":
            raise HTTPException(409, "非 pending")
        if row["requested_by"] == user["username"]:
            raise HTTPException(409, "禁止自批")
        payload = json.loads(row["payload_json"] or "{}")
        now = time.time()
        if row["action"] == "freeze_sleeve":
            conn.execute("UPDATE sleeves SET status='frozen' WHERE id=?", (row["sleeve_id"],))
        elif row["action"] == "unfreeze_sleeve":
            conn.execute("UPDATE sleeves SET status='active' WHERE id=?", (row["sleeve_id"],))
        elif row["action"] in ("raise_limit", "cut_limit"):
            max_pos = float(payload.get("max_position", 0))
            max_notional = float(payload.get("max_order_notional", 0))
            inst = payload.get("instrument_id")
            existing = conn.execute(
                "SELECT * FROM risk_limits WHERE sleeve_id=? AND IFNULL(instrument_id,-1)=IFNULL(?, -1)",
                (row["sleeve_id"], inst),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE risk_limits SET max_position=?, max_order_notional=? WHERE id=?",
                    (max_pos, max_notional, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO risk_limits(sleeve_id,instrument_id,max_position,max_order_notional,status)"
                    " VALUES(?,?,?,?,?)",
                    (row["sleeve_id"], inst, max_pos, max_notional, "active"),
                )
        conn.execute(
            "UPDATE risk_requests SET status='approved', approved_by=?, decided_at=? WHERE id=?",
            (user["username"], now, rid),
        )
        audit(conn, user["username"], "approve", "risk_request", rid, row["code"])
        conn.commit()
        return {"ok": True, "status": "approved"}


@router.post("/requests/{rid}/reject")
def reject_request(rid: int, user=Depends(require_roles("admin"))):
    with connect() as conn:
        row = conn.execute("SELECT * FROM risk_requests WHERE id=?", (rid,)).fetchone()
        if not row:
            raise HTTPException(404, "申请不存在")
        if row["status"] != "pending":
            raise HTTPException(409, "非 pending")
        conn.execute(
            "UPDATE risk_requests SET status='rejected', approved_by=?, decided_at=? WHERE id=?",
            (user["username"], time.time(), rid),
        )
        audit(conn, user["username"], "reject", "risk_request", rid, row["code"])
        conn.commit()
        return {"ok": True, "status": "rejected"}
