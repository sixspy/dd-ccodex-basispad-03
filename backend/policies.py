"""业务策略与计算辅助。"""
from __future__ import annotations

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
