"""Tests for the SignalDB adapter."""

from __future__ import annotations

import time

import pytest

from core.database import SignalDB
from tests.conftest import make_signal_row


@pytest.mark.asyncio
async def test_connect_creates_schema(db: SignalDB):
    count = await db.count_signals()
    assert count == 0


@pytest.mark.asyncio
async def test_seed_inserts_signals(db: SignalDB):
    await db.seed_demo_signals(count=20)
    assert await db.count_signals() == 20


@pytest.mark.asyncio
async def test_get_signals_returns_list(seeded_db: SignalDB):
    signals = await seeded_db.get_signals(limit=10)
    assert isinstance(signals, list)
    assert len(signals) <= 10


@pytest.mark.asyncio
async def test_get_signals_filter_ticker(db: SignalDB):
    row = make_signal_row(ticker="NVDA")
    await db._conn.execute(
        "INSERT INTO signals (id,created_at,ticker,event_type,stance,time_horizon,confidence,trend_score,quality_score,strategy,subreddit,post_title,post_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (row["id"], row["created_at"], "NVDA", "other", "bullish", "1w", 0.9, 0.5, 0.7, "none", "wsb", "test", "http://example.com"),
    )
    await db._conn.commit()
    results = await db.get_signals(ticker="NVDA")
    assert all(r["ticker"] == "NVDA" for r in results)
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_get_signals_filter_min_confidence(seeded_db: SignalDB):
    results = await seeded_db.get_signals(min_confidence=0.9)
    assert all(r["confidence"] >= 0.9 for r in results)


@pytest.mark.asyncio
async def test_get_signal_by_id_found(db: SignalDB):
    row = make_signal_row()
    await db._conn.execute(
        "INSERT INTO signals (id,created_at,ticker,event_type,stance,time_horizon,confidence,trend_score,quality_score,strategy,subreddit,post_title,post_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (row["id"], row["created_at"], row["ticker"], row["event_type"], row["stance"], row["time_horizon"], row["confidence"], row["trend_score"], row["quality_score"], row["strategy"], row["subreddit"], row["post_title"], row["post_url"]),
    )
    await db._conn.commit()
    found = await db.get_signal_by_id(row["id"])
    assert found is not None
    assert found["id"] == row["id"]


@pytest.mark.asyncio
async def test_get_signal_by_id_not_found(db: SignalDB):
    result = await db.get_signal_by_id("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_trending_tickers_returns_list(seeded_db: SignalDB):
    result = await seeded_db.get_trending_tickers(window_hours=168)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_api_key_roundtrip(db: SignalDB):
    from core.auth import generate_key, _hash_key
    key_id, raw, key_hash = generate_key()
    await db.create_api_key(key_id=key_id, key_hash=key_hash, name="test", tier="free")
    found = await db.get_key_by_hash(key_hash)
    assert found is not None
    assert found["tier"] == "free"
    assert found["name"] == "test"


@pytest.mark.asyncio
async def test_touch_key_updates_last_used(db: SignalDB):
    from core.auth import generate_key
    key_id, raw, key_hash = generate_key()
    await db.create_api_key(key_id=key_id, key_hash=key_hash, name="test", tier="free")
    await db.touch_key(key_id)
    found = await db.get_key_by_hash(key_hash)
    assert found is not None
    assert found["last_used_at"] is not None
