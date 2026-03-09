"""
ROT Signals API — FastAPI application factory.

Run locally:
    rot-api
    # or
    uvicorn api.main:app --reload

Environment:
    DATABASE_URL    path to ROT's SQLite DB (or Postgres DSN)
    SECRET_KEY      JWT signing key
    See core/config.py for full list.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from api.middleware.rate_limit import RateLimitMiddleware
from api.v1.routes import health, keys, signals, ws
from core.config import get_settings
from core.database import SignalDB

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    db = SignalDB()
    await db.connect()
    app.state.db = db
    log.info("database_connected", path=db._path)

    # Seed demo data when DB is empty (dev mode)
    count = await db.count_signals()
    if count == 0:
        log.info("seeding_demo_signals")
        await db.seed_demo_signals(count=100)

    yield

    await db.close()
    log.info("database_closed")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ROT Signals API",
        version="1.0.0",
        description="""
## Reddit Options Trader — Signal API

Turn Reddit's collective intelligence into structured, actionable options signals.

### Tiers

| Tier | Delay | Page Size | Rate Limit | WebSocket |
|------|-------|-----------|------------|-----------|
| Free | 15 min | 10 | 20 req/min | 1 conn (delayed) |
| Pro | Real-time | 200 | 300 req/min | 5 conns |
| Enterprise | Real-time | 1000 | 5000 req/min | Custom |

### Authentication

All endpoints require `X-API-Key: rot_<your-key>`.

Get a free key: `POST /v1/keys`

### Related projects

- [Reddit-Options-Trader-ROT](https://github.com/Mattbusel/Reddit-Options-Trader-ROT-) — core signal engine
- [fin-primitives](https://github.com/Mattbusel/fin-primitives) — financial market primitives
- [fin-stream](https://github.com/Mattbusel/fin-stream) — streaming market data
- [tokio-prompt-orchestrator](https://github.com/Mattbusel/tokio-prompt-orchestrator) — Rust orchestration layer
        """,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Rate limiting
    app.add_middleware(RateLimitMiddleware)

    # Routers
    app.include_router(health.router, prefix="/v1")
    app.include_router(signals.router, prefix="/v1")
    app.include_router(keys.router, prefix="/v1")
    app.include_router(ws.router, prefix="/v1")

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        reload=settings.reload,
        log_level="info",
    )


if __name__ == "__main__":
    run()
