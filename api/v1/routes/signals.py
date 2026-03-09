"""
GET /v1/signals     — paginated signal list
GET /v1/signals/{id} — single signal detail
GET /v1/signals/trending — top tickers by mention count
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from core.auth import AuthenticatedKey, resolve_api_key
from core.database import SignalDB
from core.gating import gate, gate_list
from core.models import Signal, SignalDetail, SignalList, Tier, TrendList, TickerMention

router = APIRouter(prefix="/signals", tags=["signals"])


def _db(request: Request):  # type: ignore[return]
    return request.app.state.db


def _parse_signal(raw: dict) -> Signal:
    """Build a Signal model from a raw DB row, tolerating missing fields."""
    return Signal.model_validate(raw)


@router.get("", response_model=SignalList, summary="List signals")
async def list_signals(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    ticker: str | None = None,
    stance: str | None = None,
    min_confidence: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    event_type: str | None = None,
    date_from: float | None = None,
    date_to: float | None = None,
    sort: Annotated[str | None, Query(pattern="^(created_at|confidence|trend_score)$")] = None,
    order: Annotated[str | None, Query(pattern="^(asc|desc)$")] = None,
    key: AuthenticatedKey = Depends(resolve_api_key),
    db=Depends(_db),
) -> SignalList:
    """
    Return a paginated list of options signals sourced from Reddit.

    **Free tier**: 15-minute delay, max 10 per page, reasoning redacted.
    **Pro+**: real-time, max 200 per page, full data.

    Filter by `ticker`, `stance`, `min_confidence`, `event_type`.
    Date range filtering (`date_from`/`date_to`) requires Pro+.
    """
    # Cap limit to tier maximum
    effective_limit = min(limit, key.page_limit)

    # Date range gated to paid tiers
    if not key.is_paid:
        date_from = None
        date_to = None

    raws = await db.get_signals(
        limit=effective_limit + 1,  # fetch one extra to detect has_more
        offset=offset,
        ticker=ticker,
        stance=stance,
        min_confidence=min_confidence,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
        sort=sort or "created_at",
        order=order or "desc",
    )

    has_more = len(raws) > effective_limit
    page_raws = raws[:effective_limit]
    gated = gate_list(page_raws, key)

    signals = [_parse_signal(r) for r in gated]
    total = await db.count_signals()

    return SignalList(
        signals=signals,
        total=total,
        page=offset // effective_limit if effective_limit else 0,
        page_size=effective_limit,
        has_more=has_more,
    )


@router.get("/trending", response_model=TrendList, summary="Trending tickers")
async def trending_tickers(
    request: Request,
    window_hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    key: AuthenticatedKey = Depends(resolve_api_key),
    db=Depends(_db),
) -> TrendList:
    """
    Top tickers by mention count and average confidence over the last N hours.

    Available to all tiers — useful for discovery without a paid subscription.
    """
    rows = await db.get_trending_tickers(window_hours=window_hours, limit=limit)
    return TrendList(
        tickers=[TickerMention(**r) for r in rows],
        window_hours=window_hours,
        generated_at=time.time(),
    )


@router.get("/{signal_id}", response_model=SignalDetail, summary="Get signal by ID")
async def get_signal(
    signal_id: str,
    request: Request,
    key: AuthenticatedKey = Depends(resolve_api_key),
    db=Depends(_db),
) -> SignalDetail:
    """
    Retrieve a single signal by its ID with related signals for the same ticker.

    Full reasoning and trade legs available on Pro+.
    """
    raw = await db.get_signal_by_id(signal_id)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Signal {signal_id!r} not found.")

    gated = gate(raw, key)
    signal = _parse_signal(gated)

    # Related: last 3 signals for same ticker (excluding this one)
    related_raws = await db.get_signals(
        limit=4, ticker=raw["ticker"], sort="created_at", order="desc"
    )
    related = [
        _parse_signal(gate(r, key))
        for r in related_raws
        if r["id"] != signal_id
    ][:3]

    return SignalDetail(signal=signal, related=related)
