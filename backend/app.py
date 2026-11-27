"""永续纸面基差台 — FastAPI 入口。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from audit_svc import router as audit_router
from auth import router as auth_router
from dashboard_svc import router as dashboard_router
from db import FRONTEND, PRODUCT_META, init_db
from funding_svc import router as funding_router
from history_svc import router as history_router
from instruments_svc import router as instruments_router
from locks import router as locks_router
from margin_svc import router as margin_router
from marks_svc import router as marks_router
from matcher_svc import router as matcher_router
from risk_svc import router as risk_router
from settle_svc import router as settle_router
from sleeves_svc import router as sleeves_router
from stubs_svc import router as stubs_router
from tickets_svc import router as tickets_router
from wallets_svc import router as wallets_router

PRODUCT = PRODUCT_META["name"]
SKELETON = PRODUCT_META["skeleton"]

app = FastAPI(title=PRODUCT, description=SKELETON)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    auth_router,
    dashboard_router,
    instruments_router,
    sleeves_router,
    tickets_router,
    matcher_router,
    funding_router,
    marks_router,
    margin_router,
    settle_router,
    risk_router,
    wallets_router,
    history_router,
    locks_router,
    audit_router,
    stubs_router,
):
    app.include_router(r)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    from db import DB_PATH, connect

    with connect() as conn:
        instruments = conn.execute("SELECT COUNT(*) c FROM instruments").fetchone()["c"]
        sleeves = conn.execute("SELECT COUNT(*) c FROM sleeves").fetchone()["c"]
        fills = conn.execute("SELECT COUNT(*) c FROM fills").fetchone()["c"]
        tables = conn.execute(
            "SELECT COUNT(*) c FROM sqlite_master WHERE type='table'"
        ).fetchone()["c"]
    return {
        "ok": True,
        "product": PRODUCT,
        "domain": PRODUCT_META["domain"],
        "sub_direction": PRODUCT_META["sub"],
        "skeleton": SKELETON,
        "instruments": instruments,
        "sleeves": sleeves,
        "fills": fills,
        "tables": tables,
        "db": str(DB_PATH),
    }


app.mount("/assets", StaticFiles(directory=str(FRONTEND)), name="assets")


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")
