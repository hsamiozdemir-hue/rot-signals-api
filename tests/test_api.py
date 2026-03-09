"""Integration tests — HTTP endpoints via HTTPX async client."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(app_client):
    client, _ = app_client
    resp = await client.get("/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "degraded")
    assert "version" in data
    assert "uptime_s" in data


@pytest.mark.asyncio
async def test_list_signals_requires_auth(app_client):
    client, _ = app_client
    resp = await client.get("/v1/signals")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_signals_with_valid_key(app_client):
    client, key = app_client
    resp = await client.get("/v1/signals", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    assert "signals" in data
    assert "total" in data
    assert "has_more" in data


@pytest.mark.asyncio
async def test_list_signals_invalid_key_returns_401(app_client):
    client, _ = app_client
    resp = await client.get("/v1/signals", headers={"X-API-Key": "rot_invalid_key_xyz"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_signals_free_tier_page_limit(app_client):
    client, key = app_client
    resp = await client.get("/v1/signals?limit=200", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    # Free tier caps at page_limit (10)
    assert len(data["signals"]) <= 10


@pytest.mark.asyncio
async def test_list_signals_pro_tier_higher_limit(pro_app_client):
    client, key = pro_app_client
    resp = await client.get("/v1/signals?limit=100", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["signals"]) <= 100


@pytest.mark.asyncio
async def test_list_signals_filter_by_ticker(app_client):
    client, key = app_client
    resp = await client.get("/v1/signals?ticker=AAPL", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    for sig in data["signals"]:
        assert sig["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_list_signals_filter_by_stance(app_client):
    client, key = app_client
    resp = await client.get("/v1/signals?stance=bullish", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    for sig in data["signals"]:
        assert sig["stance"] == "bullish"


@pytest.mark.asyncio
async def test_get_signal_not_found(app_client):
    client, key = app_client
    resp = await client.get("/v1/signals/nonexistent-id-xyz", headers={"X-API-Key": key})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_signal_by_id(app_client, seeded_db):
    client, key = app_client
    # Get first signal ID from list
    list_resp = await client.get("/v1/signals?limit=1", headers={"X-API-Key": key})
    assert list_resp.status_code == 200
    signals = list_resp.json()["signals"]
    if not signals:
        pytest.skip("No signals in test DB")
    signal_id = signals[0]["id"]
    detail_resp = await client.get(f"/v1/signals/{signal_id}", headers={"X-API-Key": key})
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["signal"]["id"] == signal_id
    assert "related" in data


@pytest.mark.asyncio
async def test_trending_tickers_endpoint(app_client):
    client, key = app_client
    resp = await client.get("/v1/signals/trending", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    assert "tickers" in data
    assert "window_hours" in data


@pytest.mark.asyncio
async def test_create_key_endpoint(app_client):
    client, _ = app_client
    resp = await client.post("/v1/keys", json={"name": "my-integration", "tier": "free"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"].startswith("rot_")
    assert data["tier"] == "free"
    assert "key_id" in data


@pytest.mark.asyncio
async def test_key_me_endpoint(app_client):
    client, key = app_client
    resp = await client.get("/v1/keys/me", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    assert "tier" in data
    assert "rpm_limit" in data
    assert "key" not in data  # raw key must never be returned


@pytest.mark.asyncio
async def test_rate_limit_headers_present(app_client):
    client, key = app_client
    resp = await client.get("/v1/signals", headers={"X-API-Key": key})
    assert resp.status_code == 200
    assert "x-ratelimit-limit" in resp.headers or "X-RateLimit-Limit" in resp.headers


@pytest.mark.asyncio
async def test_free_tier_fresh_signals_are_delayed(app_client, seeded_db):
    """Fresh signals (age < 15 min) must be marked as delayed for free tier."""
    import time
    from tests.conftest import make_signal_row

    # Insert a brand-new signal
    row = make_signal_row(ticker="DLYD", age_seconds=0)
    await seeded_db._conn.execute(
        "INSERT INTO signals (id,created_at,ticker,event_type,stance,time_horizon,confidence,trend_score,quality_score,strategy,subreddit,post_title,post_url) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (row["id"], row["created_at"], "DLYD", "other", "bullish", "1w", 0.9, 0.5, 0.7, "none", "wsb", "test", "http://example.com"),
    )
    await seeded_db._conn.commit()

    client, key = app_client
    resp = await client.get("/v1/signals?ticker=DLYD", headers={"X-API-Key": key})
    assert resp.status_code == 200
    data = resp.json()
    if data["signals"]:
        sig = data["signals"][0]
        # Fresh signal must be delayed for free tier
        assert sig.get("_delayed") is True or sig.get("delayed") is True
