"""保证金与强平队列。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from locks import release_lock, try_acquire_lock
from policies import (
    apply_fill_to_position,
    assert_writable_role,
    liq_code,
    liq_evidence,
    write_margin_state,
)

router = APIRouter(prefix="/api/margin", tags=["margin"])

LEVERAGE_DEFAULT = 5.0



class EnqueueLiqBody(BaseModel):
    sleeve_id: int
    instrument_id: int
    qty: float | None = None
    note: str = ""


@router.get("/states")
def list_states(user=Depends(current_user)):
    """保证金页数据源：状态按正式强平凭据推导，库内 liquidated 无凭据不展示。"""
    with connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM margin_states ORDER BY sleeve_id").fetchall()]
        for row in rows:
            ev = liq_evidence(conn, row["sleeve_id"])
            row["status_stored"] = row["status"]
            row["liq_evidence_ok"] = not ev["violations"] and not ev["queued"]
            if ev["violations"]:
                row["status"] = "liquidating" if ev["queued"] else "call"
                row["status_source"] = "reconciled"
            elif ev["official_flat"]:
                row["status"] = "liquidated"
                row["status_source"] = "official"
            elif ev["queued"]:
                # 有排队强平但未成交：只能是处理中，绝不是已清算
                row["status"] = "liquidating"
                row["status_source"] = "official"
            else:
                row["status_source"] = "official"
        return rows


@router.post("/recompute/{sleeve_id}")
def recompute(sleeve_id: int, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        sleeve = conn.execute("SELECT * FROM sleeves WHERE id=?", (sleeve_id,)).fetchone()
        if not sleeve:
            raise HTTPException(404, "策略簿不存在")
        write_margin_state(conn, sleeve_id, LEVERAGE_DEFAULT)
        audit(conn, user["username"], "recompute", "margin", sleeve_id, sleeve["code"])
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM margin_states WHERE sleeve_id=?", (sleeve_id,)).fetchone())


@router.get("/liquidations")
def list_liqs(status: str | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM liquidation_queue"
    args: list = []
    if status:
        sql += " WHERE status=?"
        args.append(status)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.post("/liquidations/enqueue")
def enqueue_liq(body: EnqueueLiqBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    with connect() as conn:
        pos = conn.execute(
            "SELECT * FROM positions WHERE sleeve_id=? AND instrument_id=?",
            (body.sleeve_id, body.instrument_id),
        ).fetchone()
        if not pos or abs(pos["qty"]) < 1e-12:
            raise HTTPException(409, "无仓可强平")
        mark = conn.execute(
            "SELECT mark FROM mark_prices WHERE instrument_id=?", (body.instrument_id,)
        ).fetchone()
        if not mark:
            raise HTTPException(409, "缺标记价")
        qty = body.qty if body.qty is not None else abs(pos["qty"])
        n = conn.execute("SELECT COUNT(*) c FROM liquidation_queue").fetchone()["c"] + 1
        code = liq_code(n)
        now = time.time()
        cur = conn.execute(
            "INSERT INTO liquidation_queue(code,sleeve_id,instrument_id,qty,trigger_mark,status,created_at,executed_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (code, body.sleeve_id, body.instrument_id, qty, mark["mark"], "queued", now, None, body.note),
        )
        lid = cur.lastrowid
        write_margin_state(conn, body.sleeve_id, LEVERAGE_DEFAULT, now=now)
        audit(conn, user["username"], "enqueue", "liquidation", lid, code)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM liquidation_queue WHERE id=?", (lid,)).fetchone())


def _record_contention(conn, lid: int, actor: str, reason: str, holder: str | None = None) -> None:
    """争用段：败方只记争用痕，不碰任何正式区（取舍另在交班说明，不入正式表）。"""
    if conn.in_transaction:
        conn.commit()
    detail = f"actor={actor} liq:{lid} 争用失败 reason={reason}"
    if holder:
        detail += f" held_by={holder}"
    conn.execute(
        "INSERT INTO audit_logs(actor,action,entity,entity_id,detail,created_at) VALUES(?,?,?,?,?,?)",
        (actor, "execute_contended", "liquidation", str(lid), detail, time.time()),
    )
    conn.commit()


@router.post("/liquidations/{lid}/execute")
def execute_liq(lid: int, user=Depends(require_roles("admin", "trader"))):
    """正式强平路径（甲口径）。

    同事务内：写正式强平成交 -> 回写仓位 -> 队列升 executed -> 重算保证金。
    任一步失败（含缺成交）整笔零增回滚，队列保持 queued。
    抢锁失败方零正式改，只记争用痕。
    """
    assert_writable_role(user["role"])
    resource = f"liq:{lid}"
    holder = user["username"]
    conn = connect()
    try:
        ok, current = try_acquire_lock(conn, resource, holder, "execute_liq")
        if not ok:
            _record_contention(conn, lid, holder, "lock_held", current)
            raise HTTPException(409, f"资源锁定中: {resource} by {current}")
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                item = conn.execute(
                    "SELECT * FROM liquidation_queue WHERE id=?", (lid,)
                ).fetchone()
                if not item:
                    raise HTTPException(404, "强平单不存在")
                if item["status"] != "queued":
                    # 抢到锁但正式区已被他人推进：同样属争用败方，只记痕
                    _record_contention(conn, lid, holder, "already_" + item["status"])
                    raise HTTPException(409, "状态不可执行")
                if conn.execute("SELECT 1 FROM settle_batches WHERE status='locked'").fetchone():
                    raise HTTPException(409, "结算锁定中禁止强平")
                pos = conn.execute(
                    "SELECT * FROM positions WHERE sleeve_id=? AND instrument_id=?",
                    (item["sleeve_id"], item["instrument_id"]),
                ).fetchone()
                if not pos or abs(pos["qty"]) < 1e-12:
                    raise HTTPException(409, "仓位已空")
                side = "sell" if pos["qty"] > 0 else "buy"
                px = item["trigger_mark"]
                qty = min(item["qty"], abs(pos["qty"]))
                if qty <= 0:
                    raise HTTPException(409, "强平数量非法")
                now = time.time()
                n = conn.execute(
                    "SELECT COALESCE(MAX(id),0) m FROM fills"
                ).fetchone()["m"]
                fcode = f"FIL-{n + 1:05d}"
                while conn.execute("SELECT 1 FROM fills WHERE code=?", (fcode,)).fetchone():
                    n += 1
                    fcode = f"FIL-{n + 1:05d}"
                # 1) 正式强平成交
                cur = conn.execute(
                    "INSERT INTO fills(code,ticket_id,sleeve_id,instrument_id,side,price,qty,fee,source,created_at,note)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        fcode,
                        None,
                        item["sleeve_id"],
                        item["instrument_id"],
                        side,
                        px,
                        qty,
                        0,
                        "liquidation",
                        now,
                        item["code"],
                    ),
                )
                if cur.rowcount != 1:
                    conn.rollback()
                    raise HTTPException(500, "强平成交写入失败")
                # 2) 仓位回写
                new_qty, new_avg, realized = apply_fill_to_position(
                    pos["qty"], pos["avg_entry"], side, qty, px
                )
                upd = conn.execute(
                    "UPDATE positions SET qty=?, avg_entry=?, realized_pnl=?, updated_at=? WHERE id=?",
                    (new_qty, new_avg, pos["realized_pnl"] + realized, now, pos["id"]),
                )
                if upd.rowcount != 1:
                    conn.rollback()
                    raise HTTPException(500, "仓位回写失败")
                # 3) 队列升 executed，带成交号与仓位边差额
                upd = conn.execute(
                    "UPDATE liquidation_queue SET status='executed', executed_at=?,"
                    " fill_code=?, remaining_qty=? WHERE id=? AND status='queued'",
                    (now, fcode, new_qty, lid),
                )
                if upd.rowcount != 1:
                    conn.rollback()
                    raise HTTPException(409, "强平状态已被并发修改")
                # 4) 保证金同源重算（占用随仓位边即时可见）
                mstate = write_margin_state(
                    conn, item["sleeve_id"], LEVERAGE_DEFAULT, now=now
                )
                audit(
                    conn,
                    holder,
                    "execute",
                    "liquidation",
                    lid,
                    f"成交号={fcode} 仓位边差额={qty} 剩余={new_qty}"
                    f" 保证金占用={mstate.get('used_margin', 0.0)}",
                )
                conn.commit()
                return {
                    "ok": True,
                    "fill_code": fcode,
                    "remaining_qty": new_qty,
                    "position_delta": qty,
                    "liquidation_id": lid,
                }
            except HTTPException:
                conn.rollback()
                raise
            except Exception:
                conn.rollback()
                raise
        finally:
            release_lock(conn, resource, holder)
            conn.commit()
    finally:
        conn.close()
