"""会话鉴权。"""
from __future__ import annotations

import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from db import connect
from models import USERS

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


def current_user(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization[7:].strip()
    with connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        if not row:
            raise HTTPException(401, "会话无效")
        return {"username": row["username"], "role": row["role"], "token": token}


def require_roles(*roles: str):
    def _dep(authorization: Annotated[str | None, Header()] = None) -> dict:
        user = current_user(authorization)
        if user["role"] not in roles and user["role"] != "admin":
            raise HTTPException(403, "权限不足")
        return user

    return _dep


@router.post("/login")
def login(body: LoginBody):
    meta = USERS.get(body.username)
    if not meta or meta["password"] != body.password:
        raise HTTPException(401, "用户名或密码错误")
    token = secrets.token_hex(16)
    with connect() as conn:
        conn.execute(
            "INSERT INTO sessions(token,username,role,created_at) VALUES(?,?,?,?)",
            (token, body.username, meta["role"], time.time()),
        )
        conn.commit()
    return {
        "token": token,
        "username": body.username,
        "role": meta["role"],
        "display": meta["display"],
    }


@router.get("/me")
def me(authorization: Annotated[str | None, Header()] = None):
    user = current_user(authorization)
    meta = USERS[user["username"]]
    return {**user, "display": meta["display"]}


@router.post("/logout")
def logout(authorization: Annotated[str | None, Header()] = None):
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        with connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            conn.commit()
    return {"ok": True}
