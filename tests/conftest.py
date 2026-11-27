"""强平执行案测试夹具：每个用例独立临时库，互不污染。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import db as dbmod  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    """临时库 + TestClient；测试结束恢复全局 DB_PATH。"""
    old_path = dbmod.DB_PATH
    dbmod.DB_PATH = tmp_path / "app.db"
    dbmod.init_db()
    try:
        from app import app

        from fastapi.testclient import TestClient

        # 服务端异常按 500 响应返回，便于断言「失败即整笔回滚」而非测试器直接抛出
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        dbmod.DB_PATH = old_path


@pytest.fixture()
def login(client):
    def _login(username: str = "trader", password: str = "trader123") -> dict:
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return _login


@pytest.fixture()
def db_conn():
    """直连当前测试库，用于构造不一致现场。"""
    conn = dbmod.connect()
    try:
        yield conn
    finally:
        conn.close()
