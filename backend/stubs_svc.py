"""题面空桩：链上预言机 / CEX 行情桥。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from auth import current_user

router = APIRouter(prefix="/api/stubs", tags=["stubs"])


@router.get("")
def list_stubs(user=Depends(current_user)):
    return [
        {
            "key": "chain_oracle",
            "title": "链上预言机桥",
            "status": "not_implemented",
            "path": "/api/stubs/chain_oracle",
        },
        {
            "key": "cex_bridge",
            "title": "中心化所行情桥",
            "status": "not_implemented",
            "path": "/api/stubs/cex_bridge",
        },
    ]


@router.get("/chain_oracle")
@router.post("/chain_oracle")
def chain_oracle(user=Depends(current_user)):
    return JSONResponse(
        status_code=501,
        content={"detail": "chain_oracle 空桩未实现", "stub": "chain_oracle"},
    )


@router.get("/cex_bridge")
@router.post("/cex_bridge")
def cex_bridge(user=Depends(current_user)):
    return JSONResponse(
        status_code=501,
        content={"detail": "cex_bridge 空桩未实现", "stub": "cex_bridge"},
    )
