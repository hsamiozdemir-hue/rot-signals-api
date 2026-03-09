"""GET /v1/health — liveness + readiness probe."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from core.models import HealthResponse

router = APIRouter(tags=["meta"])

_START_TIME = time.time()
_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health(request: Request) -> HealthResponse:
    db = request.app.state.db
    try:
        count = await db.count_signals()
        db_ok = True
    except Exception:
        count = 0
        db_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=_VERSION,
        db_connected=db_ok,
        signal_count=count,
        uptime_s=time.time() - _START_TIME,
    )
