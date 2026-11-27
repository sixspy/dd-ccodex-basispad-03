"""链上出入金纸面台账。"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import current_user, require_roles
from db import audit, connect, row_to_dict
from models import WALLET_KINDS, WALLET_TX_KINDS
from policies import assert_writable_role

router = APIRouter(prefix="/api/wallets", tags=["wallets"])


class WalletBody(BaseModel):
    code: str
    title: str
    kind: str = "hot"
    chain: str = "ethereum"
    address: str
    balance: float = 0
    status: str = "active"
    note: str = ""


class TxBody(BaseModel):
    code: str
    wallet_id: int
    kind: str
    amount: float
    tx_hash: str = ""
    sleeve_id: int | None = None
    note: str = ""


@router.get("")
def list_wallets(user=Depends(current_user)):
    with connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM wallets ORDER BY id").fetchall()]


@router.post("")
def create_wallet(body: WalletBody, user=Depends(require_roles("admin"))):
    if body.kind not in WALLET_KINDS:
        raise HTTPException(400, "kind 非法")
    with connect() as conn:
        if conn.execute("SELECT 1 FROM wallets WHERE code=?", (body.code,)).fetchone():
            raise HTTPException(409, "code 已存在")
        cur = conn.execute(
            "INSERT INTO wallets(code,title,kind,chain,address,balance,status,note) VALUES(?,?,?,?,?,?,?,?)",
            (body.code, body.title, body.kind, body.chain, body.address, body.balance, body.status, body.note),
        )
        wid = cur.lastrowid
        audit(conn, user["username"], "create", "wallet", wid, body.code)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM wallets WHERE id=?", (wid,)).fetchone())


@router.get("/txs")
def list_txs(wallet_id: int | None = None, user=Depends(current_user)):
    sql = "SELECT * FROM wallet_txs WHERE 1=1"
    args: list = []
    if wallet_id:
        sql += " AND wallet_id=?"
        args.append(wallet_id)
    sql += " ORDER BY id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.execute(sql, args).fetchall()]


@router.post("/txs")
def create_tx(body: TxBody, user=Depends(require_roles("admin", "trader"))):
    assert_writable_role(user["role"])
    if body.kind not in WALLET_TX_KINDS:
        raise HTTPException(400, "kind 非法")
    with connect() as conn:
        wallet = conn.execute("SELECT * FROM wallets WHERE id=?", (body.wallet_id,)).fetchone()
        if not wallet:
            raise HTTPException(404, "钱包不存在")
        if wallet["status"] != "active":
            raise HTTPException(409, "钱包不可用")
        if conn.execute("SELECT 1 FROM wallet_txs WHERE code=?", (body.code,)).fetchone():
            raise HTTPException(409, "code 已存在")
        bal = wallet["balance"]
        if body.kind == "deposit":
            bal += body.amount
        elif body.kind == "withdraw":
            if body.amount > wallet["balance"]:
                raise HTTPException(409, "余额不足")
            bal -= body.amount
        now = time.time()
        cur = conn.execute(
            "INSERT INTO wallet_txs(code,wallet_id,kind,amount,tx_hash,status,sleeve_id,created_at,note)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (body.code, body.wallet_id, body.kind, body.amount, body.tx_hash, "posted", body.sleeve_id, now, body.note),
        )
        tid = cur.lastrowid
        conn.execute("UPDATE wallets SET balance=? WHERE id=?", (bal, body.wallet_id))
        if body.sleeve_id and body.kind == "deposit":
            conn.execute(
                "UPDATE sleeves SET base_equity = base_equity + ? WHERE id=?",
                (body.amount, body.sleeve_id),
            )
        if body.sleeve_id and body.kind == "withdraw":
            conn.execute(
                "UPDATE sleeves SET base_equity = base_equity - ? WHERE id=?",
                (body.amount, body.sleeve_id),
            )
        audit(conn, user["username"], "wallet_tx", "wallet_tx", tid, body.code)
        conn.commit()
        return row_to_dict(conn.execute("SELECT * FROM wallet_txs WHERE id=?", (tid,)).fetchone())
