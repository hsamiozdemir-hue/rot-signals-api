"""Shared pytest fixtures for rot-signals-api tests."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from api.main import create_app
from core.auth import _hash_key, generate_key
from core.database import SignalDB


@pytest_asyncio.fixture
async def db(tmp_path) -> AsyncIterator[SignalDB]:
    db_path = str(tmp_path / "test.db")
    database = SignalDB(db_path=db_path)
    await database.connect()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def seeded_db(db: SignalDB) -> SignalDB:
    await db.seed_demo_signals(count=30)
    return db


@pytest_asyncio.fixture
async def free_key(db: SignalDB) -> str:
    key_id, raw, key_hash = generate_key()
    await db.create_api_key(key_id=key_id, key_hash=key_hash, name="test-free", tier="free")
    return raw


@pytest_asyncio.fixture
async def pro_key(db: SignalDB) -> str:
    key_id, raw, key_hash = generate_key()
    await db.create_api_key(key_id=key_id, key_hash=key_hash, name="test-pro", tier="pro")
    return raw


@pytest_asyncio.fixture
async def app_client(seeded_db: SignalDB, free_key: str):
    """HTTPX async client wired to a test app instance with seeded DB."""
    application = create_app()
    application.state.db = seeded_db

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        yield client, free_key


@pytest_asyncio.fixture
async def pro_app_client(seeded_db: SignalDB, pro_key: str):
    application = create_app()
    application.state.db = seeded_db

    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        yield client, pro_key


def make_signal_row(
    ticker: str = "AAPL",
    stance: str = "bullish",
    confidence: float = 0.85,
    age_seconds: float = 0,
    strategy: str = "debit_spread",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "created_at": time.time() - age_seconds,
        "ticker": ticker,
        "event_type": "earnings_rumor",
        "stance": stance,
        "time_horizon": "1w",
        "confidence": confidence,
        "trend_score": 0.7,
        "quality_score": 0.8,
        "strategy": strategy,
        "subreddit": "wallstreetbets",
        "post_title": f"{ticker} looking good",
        "post_url": "https://reddit.com/r/test/comments/abc123",
        "sector": "Technology",
        "ai_summary": "Strong bullish momentum detected.",
        "market_data": {"price": 150.0, "iv_rank": 0.6},
        "reasoning": {"thesis": "Earnings beat incoming", "invalidations": ["misses guidance"]},
        "trade_idea": {"strategy": strategy, "legs": [{"side": "buy", "kind": "call", "strike": 155.0, "expiry": "2025-01-17", "qty": 1}], "quality_score": 0.8},
    }
