"""
Canonical Pydantic v2 models for the ROT Signals public API.

These are the wire-format types — separate from ROT's internal dataclasses
so the API contract can evolve independently of the core engine.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class Stance(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Horizon(str, Enum):
    INTRADAY = "intraday"
    ONE_WEEK = "1w"
    EARNINGS = "earnings"
    LONGER = "longer"
    UNKNOWN = "unknown"


class EventType(str, Enum):
    EARNINGS_RUMOR = "earnings_rumor"
    PRODUCT_NEWS = "product_news"
    REGULATORY = "regulatory"
    SQUEEZE_CHATTER = "squeeze_chatter"
    MACRO = "macro"
    OTHER = "other"


class Strategy(str, Enum):
    DEBIT_SPREAD = "debit_spread"
    CREDIT_SPREAD = "credit_spread"
    IRON_CONDOR = "iron_condor"
    CALENDAR = "calendar"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    NONE = "none"


class Tier(str, Enum):
    FREE = "free"
    PRO = "pro"
    PREMIUM = "premium"
    ULTRA = "ultra"
    ENTERPRISE = "enterprise"


# ── Signal sub-models ─────────────────────────────────────────────────────────

class OptionLeg(BaseModel):
    side: str
    kind: str
    strike: float
    expiry: str
    qty: int


class TradeIdea(BaseModel):
    strategy: Strategy
    legs: list[OptionLeg] = Field(default_factory=list)
    max_loss: float | None = None
    thesis: str = ""
    time_stop: str = ""
    quality_score: float = 0.0
    # Free tier: legs and thesis are redacted
    locked: bool = Field(default=False, alias="_locked")
    upgrade_message: str | None = Field(default=None, alias="_upgrade_message")

    model_config = {"populate_by_name": True}


class Reasoning(BaseModel):
    thesis: str = ""
    catalyst_window: str = ""
    market_expectation: str = ""
    invalidations: list[str] = Field(default_factory=list)
    recommended_structures: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    # Free tier: redacted
    locked: bool = Field(default=False, alias="_locked")
    upgrade_message: str | None = Field(default=None, alias="_upgrade_message")

    model_config = {"populate_by_name": True}


class MarketData(BaseModel):
    price: float | None = None
    volume: int | None = None
    iv: float | None = None           # implied volatility
    iv_rank: float | None = None
    change_pct: float | None = None
    market_cap: float | None = None


# ── Primary signal model ──────────────────────────────────────────────────────

class Signal(BaseModel):
    """
    A fully-gated signal as returned by the API.

    Free tier: 15-minute delay, reasoning/legs redacted.
    Pro+: real-time, full data.
    """
    id: str
    created_at: float          # Unix timestamp
    ticker: str
    event_type: EventType
    stance: Stance
    time_horizon: Horizon
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    trend_score: float
    quality_score: float
    strategy: Strategy
    subreddit: str
    post_title: str
    post_url: str
    sector: str | None = None
    ai_summary: str | None = None
    market_data: MarketData | None = None
    reasoning: Reasoning | None = None
    trade_idea: TradeIdea | None = None

    # Delay metadata — present when free-tier signal is not yet available
    delayed: bool = Field(default=False, alias="_delayed")
    available_in_s: int | None = Field(default=None, alias="_available_in_s")

    model_config = {"populate_by_name": True}


# ── List / pagination wrappers ────────────────────────────────────────────────

class SignalList(BaseModel):
    signals: list[Signal]
    total: int
    page: int
    page_size: int
    has_more: bool


class SignalDetail(BaseModel):
    signal: Signal
    related: list[Signal] = Field(default_factory=list)


# ── Auth models ───────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    tier: Tier = Tier.FREE


class APIKeyResponse(BaseModel):
    key: str       # shown once on creation
    key_id: str
    name: str
    tier: Tier
    created_at: float
    rpm_limit: int


class APIKeyInfo(BaseModel):
    key_id: str
    name: str
    tier: Tier
    created_at: float
    last_used_at: float | None
    rpm_limit: int
    # key itself is never returned after initial creation


# ── Ticker / trend models ─────────────────────────────────────────────────────

class TickerMention(BaseModel):
    ticker: str
    mention_count: int
    bullish_count: int
    bearish_count: int
    avg_confidence: float
    latest_signal_at: float | None
    trend_score: float


class TrendList(BaseModel):
    tickers: list[TickerMention]
    window_hours: int
    generated_at: float


# ── WebSocket message types ───────────────────────────────────────────────────

class WSMessageType(str, Enum):
    SIGNAL = "signal"
    HEARTBEAT = "heartbeat"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    ERROR = "error"
    AUTH = "auth"


class WSMessage(BaseModel):
    type: WSMessageType
    data: Any = None
    ts: float = 0.0


class WSSubscribePayload(BaseModel):
    tickers: list[str] = Field(default_factory=list)    # empty = all
    min_confidence: float = 0.0
    stances: list[Stance] = Field(default_factory=list)


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    db_connected: bool
    signal_count: int
    uptime_s: float
