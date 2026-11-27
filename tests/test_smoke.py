"""冒烟：健康检查、登录、主链路只读与一笔撮合。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("BASISPAD_TEST", "1")

# 使用临时库
import db as dbmod

dbmod.DB_PATH = ROOT / "data" / "test_app.db"
if dbmod.DB_PATH.exists():
    dbmod.DB_PATH.unlink()

from app import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    dbmod.init_db()
    with TestClient(app) as c:
        yield c


def _login(client, username="trader", password="trader123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_domain(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["domain"] == "其它垂类行业"
    assert body["sub_direction"] == "web3 区块链 量化交易"
    assert body["instruments"] >= 1
    assert body["sleeves"] >= 1


def test_login_and_summary(client):
    h = _login(client)
    r = client.get("/api/dashboard/summary", headers=h)
    assert r.status_code == 200
    assert "fills" in r.json()


def test_list_core_tables(client):
    h = _login(client)
    for path in (
        "/api/instruments",
        "/api/sleeves",
        "/api/tickets",
        "/api/matcher/fills",
        "/api/funding/snapshots",
        "/api/marks",
        "/api/margin/states",
        "/api/settle/batches",
        "/api/risk/limits",
        "/api/wallets",
        "/api/stubs",
    ):
        r = client.get(path, headers=h)
        assert r.status_code == 200, path
        assert isinstance(r.json(), list)


def test_stubs_501(client):
    h = _login(client)
    r = client.get("/api/stubs/chain_oracle", headers=h)
    assert r.status_code == 501
    r2 = client.get("/api/stubs/cex_bridge", headers=h)
    assert r2.status_code == 501


def test_match_open_ticket(client):
    h = _login(client)
    # TKT-0003 is open
    tickets = client.get("/api/tickets", headers=h).json()
    open_ones = [t for t in tickets if t["status"] == "open" and t["order_type"] == "limit" and t["price"]]
    assert open_ones
    tid = open_ones[0]["id"]
    r = client.post("/api/matcher/match", headers=h, json={"ticket_id": tid, "fill_qty": open_ones[0]["qty"]})
    assert r.status_code == 200, r.text
    assert r.json()["ticket_status"] in ("filled", "partial")
