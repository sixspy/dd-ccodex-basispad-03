"""业务策略与计算辅助。"""
from __future__ import annotations

import time

from fastapi import HTTPException


def assert_writable_role(role: str) -> None:
    if role == "viewer":
        raise HTTPException(403, "只读账号禁止写入")


def round_px(px: float, tick: float) -> float:
    if tick <= 0:
        return px
    return round(round(px / tick) * tick, 10)


def round_qty(qty: float, lot: float) -> float:
    if lot <= 0:
        return qty
    return round(round(qty / lot) * lot, 10)


def notional(price: float, qty: float) -> float:
    return abs(price * qty)


def funding_payment(position_qty: float, rate: float, mark: float) -> float:
    """多头支付正费率；空头收取。"""
    return -position_qty * mark * rate


def unrealized_pnl(qty: float, avg_entry: float, mark: float) -> float:
    return qty * (mark - avg_entry)


def used_margin(qty: float, mark: float, leverage: float) -> float:
    lev = max(leverage, 0.01)
    return abs(qty * mark) / lev


def available_equity(equity: float, used: float) -> float:
    return equity - used


def should_liquidate(equity: float, used: float, maintain_ratio: float = 0.05) -> bool:
    if used <= 0:
        return False
    return equity / used < maintain_ratio


def apply_fill_to_position(qty: float, avg: float, fill_side: str, fill_qty: float, fill_px: float):
    signed = fill_qty if fill_side == "buy" else -fill_qty
    new_qty = qty + signed
    if qty == 0 or (qty > 0 and signed > 0) or (qty < 0 and signed < 0):
        # 同向加仓
        total = abs(qty) + fill_qty
        new_avg = ((abs(qty) * avg) + (fill_qty * fill_px)) / total if total else fill_px
        realized = 0.0
    elif abs(signed) <= abs(qty) and ((qty > 0 and signed < 0) or (qty < 0 and signed > 0)):
        # 减仓
        realized = (fill_px - avg) * (-signed if qty > 0 else signed)
        # 简化：部分平仓均价不变
        new_avg = avg if new_qty != 0 else 0.0
        if new_qty == 0:
            new_avg = 0.0
    else:
        # 反向翻仓
        close_qty = abs(qty)
        realized = (fill_px - avg) * (close_qty if qty > 0 else -close_qty)
        open_qty = abs(new_qty)
        new_avg = fill_px if open_qty else 0.0
    return new_qty, new_avg, realized


def settle_batch_code(seq: int) -> str:
    return f"SET-{seq:04d}"


def liq_code(seq: int) -> str:
    return f"LIQ-{seq:04d}"


# ---------------------------------------------------------------------------
# 强平案（basispad-03）· 保证金同源与账实联查
# ---------------------------------------------------------------------------
EPS = 1e-9


def derive_margin_status(equity: float, used: float) -> tuple[str, float]:
    """按权益/占用推导保证金状态；不落库，供写口与页面共用。"""
    avail = available_equity(equity, used)
    if should_liquidate(equity, used):
        return "liquidating", avail
    if avail < 0:
        return "call", avail
    if avail < equity * 0.2:
        return "warn", avail
    return "ok", avail


def compute_margin(conn, sleeve_id: int, leverage: float = 5.0) -> dict | None:
    """按当前仓位与标记价计算保证金快照（与撮合/强平同源）。"""
    sleeve = conn.execute("SELECT * FROM sleeves WHERE id=?", (sleeve_id,)).fetchone()
    if not sleeve:
        return None
    positions = conn.execute(
        "SELECT * FROM positions WHERE sleeve_id=?", (sleeve_id,)
    ).fetchall()
    used = 0.0
    upnl = 0.0
    realized = 0.0
    for p in positions:
        mark_row = conn.execute(
            "SELECT mark FROM mark_prices WHERE instrument_id=?", (p["instrument_id"],)
        ).fetchone()
        mark = mark_row["mark"] if mark_row else p["avg_entry"]
        used += used_margin(p["qty"], mark, leverage)
        upnl += unrealized_pnl(p["qty"], p["avg_entry"], mark)
        realized += p["realized_pnl"]
    equity = sleeve["base_equity"] + realized + upnl
    status, avail = derive_margin_status(equity, used)
    flat = all(abs(p["qty"]) < EPS for p in positions)
    return {
        "sleeve_id": sleeve_id,
        "equity": equity,
        "used_margin": used,
        "available": avail,
        "status": status,
        "flat": flat,
    }


def liq_evidence(conn, sleeve_id: int) -> dict:
    """强平账实联查：队列、成交、仓位三边对账，不写任何正式区。"""
    liqs = conn.execute(
        "SELECT * FROM liquidation_queue WHERE sleeve_id=? ORDER BY id", (sleeve_id,)
    ).fetchall()
    positions = conn.execute(
        "SELECT * FROM positions WHERE sleeve_id=?", (sleeve_id,)
    ).fetchall()
    flat = all(abs(p["qty"]) < EPS for p in positions)
    violations: list[dict] = []
    executed: list[dict] = []
    queued = 0
    first_open_liq = None
    for r in liqs:
        if r["status"] == "queued":
            queued += 1
            first_open_liq = first_open_liq or r["id"]
            continue
        if r["status"] != "executed":
            violations.append(
                {
                    "kind": "unexpected_liq_status",
                    "sleeve_id": sleeve_id,
                    "liq_id": r["id"],
                    "status": r["status"],
                }
            )
            continue
        fill = None
        if r["fill_code"]:
            fill = conn.execute(
                "SELECT * FROM fills WHERE code=? AND source='liquidation'",
                (r["fill_code"],),
            ).fetchone()
        if not fill:
            # 兼容旧行：以 note 回指 LIQ 编码 + 簿/标的联查
            fill = conn.execute(
                "SELECT * FROM fills WHERE source='liquidation' AND sleeve_id=?"
                " AND instrument_id=? AND note=?",
                (r["sleeve_id"], r["instrument_id"], r["code"]),
            ).fetchone()
        if not fill:
            violations.append(
                {
                    "kind": "executed_without_fill",
                    "sleeve_id": sleeve_id,
                    "liq_id": r["id"],
                    "code": r["code"],
                }
            )
            continue
        executed.append({"liq": dict(r), "fill": dict(fill)})
        if r["remaining_qty"] is not None:
            pos = next(
                (p for p in positions if p["instrument_id"] == r["instrument_id"]), None
            )
            pos_qty = pos["qty"] if pos else 0.0
            if abs(pos_qty - r["remaining_qty"]) > 1e-6:
                violations.append(
                    {
                        "kind": "position_mismatch",
                        "sleeve_id": sleeve_id,
                        "liq_id": r["id"],
                        "expected_qty": r["remaining_qty"],
                        "actual_qty": pos_qty,
                    }
                )
    official_flat = bool(executed) and flat
    margin_row = conn.execute(
        "SELECT status FROM margin_states WHERE sleeve_id=?", (sleeve_id,)
    ).fetchone()
    if margin_row and margin_row["status"] == "liquidated" and not official_flat:
        violations.append(
            {
                "kind": "liquidated_without_fill",
                "sleeve_id": sleeve_id,
                "liq_id": first_open_liq,
                "detail": "保证金行标已清算，但无正式强平成交或仓位未平",
            }
        )
    return {
        "sleeve_id": sleeve_id,
        "queued": queued,
        "executed": executed,
        "flat": flat,
        "official_flat": official_flat,
        "violations": violations,
    }


def write_margin_state(conn, sleeve_id: int, leverage: float = 5.0, now: float | None = None) -> dict:
    """重算并落保证金行；已清算只认正式强平凭据，禁止无成交标 liquidated。"""
    data = compute_margin(conn, sleeve_id, leverage)
    if data is None:
        return {}
    ev = liq_evidence(conn, sleeve_id)
    if ev["official_flat"]:
        data["status"] = "liquidated"
    elif ev["queued"]:
        data["status"] = "liquidating"
    conn.execute(
        "INSERT INTO margin_states(sleeve_id,equity,used_margin,available,status,liq_price_hint,updated_at)"
        " VALUES(?,?,?,?,?,?,?) ON CONFLICT(sleeve_id) DO UPDATE SET"
        " equity=excluded.equity, used_margin=excluded.used_margin, available=excluded.available,"
        " status=excluded.status, updated_at=excluded.updated_at",
        (
            sleeve_id,
            data["equity"],
            data["used_margin"],
            data["available"],
            data["status"],
            None,
            now if now is not None else time.time(),
        ),
    )
    return data
