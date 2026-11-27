"""领域常量与用户。"""
from __future__ import annotations

PRODUCT_NAME = "永续纸面基差台"
SKELETON = (
    "量化纸面台按永续标的与策略簿下单撮合，"
    "资金费率与标记价同源入账，结算封批与强平队列互锁，"
    "链上出入金只记账不直连主网。"
)
DOMAIN = "其它垂类行业"
SUB_DIRECTION = "web3 区块链 量化交易"

USERS = {
    "admin": {"password": "admin123", "role": "admin", "display": "管理员"},
    "trader": {"password": "trader123", "role": "trader", "display": "交易员"},
    "viewer": {"password": "viewer123", "role": "viewer", "display": "只读"},
}

INSTRUMENT_KINDS = ("perp", "inverse_perp", "dated_future")
SLEEVE_STATUSES = ("active", "frozen", "archived")
TICKET_STATUSES = ("open", "partial", "filled", "cancelled", "rejected")
SIDES = ("buy", "sell")
ORDER_TYPES = ("limit", "market", "post_only")
FILL_SOURCES = ("matcher", "liquidation", "settlement_adj")
FUNDING_STATUSES = ("draft", "accrued", "settled", "void")
MARK_STATUSES = ("live", "frozen", "stale")
MARGIN_STATUSES = ("ok", "warn", "call", "liquidating", "liquidated")
SETTLE_STATUSES = ("draft", "locked", "official", "void")
RISK_ACTIONS = ("raise_limit", "cut_limit", "freeze_sleeve", "unfreeze_sleeve")
WALLET_KINDS = ("hot", "cold", "exchange_sub")
WALLET_TX_KINDS = ("deposit", "withdraw", "internal_transfer")
