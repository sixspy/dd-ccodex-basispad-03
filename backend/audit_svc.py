"""审计与强平账实联查。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import current_user
from db import connect
from policies import liq_evidence

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(limit: int = 100, user=Depends(current_user)):
    limit = max(1, min(limit, 500))
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/liq_recon")
def liq_recon(user=Depends(current_user)):
    """跨表账实联查：强平队列 / 强平成交 / 仓位边 / 保证金，只读不写。"""
    with connect() as conn:
        sleeve_ids = [r["sleeve_id"] for r in conn.execute("SELECT DISTINCT sleeve_id FROM liquidation_queue")]
        for r in conn.execute("SELECT DISTINCT sleeve_id FROM margin_states"):
            if r["sleeve_id"] not in sleeve_ids:
                sleeve_ids.append(r["sleeve_id"])
        details = []
        violations: list[dict] = []
        queued = executed = 0
        for sid in sorted(sleeve_ids):
            ev = liq_evidence(conn, sid)
            queued += ev["queued"]
            executed += len(ev["executed"])
            violations.extend(ev["violations"])
            details.append(
                {
                    "sleeve_id": sid,
                    "queued": ev["queued"],
                    "executed": len(ev["executed"]),
                    "flat": ev["flat"],
                    "official_flat": ev["official_flat"],
                    "violations": len(ev["violations"]),
                }
            )
        contended = conn.execute(
            "SELECT COUNT(*) c FROM audit_logs WHERE action='execute_contended'"
        ).fetchone()["c"]
        return {
            "ok": not violations,
            "queued": queued,
            "executed": executed,
            "contended": int(contended),
            "violations": violations,
            "sleeves": details,
        }
