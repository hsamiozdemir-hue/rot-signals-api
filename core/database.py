"""
Database adapter — reads ROT's signal database.

Uses aiosqlite for async SQLite access. Swap the query layer
for asyncpg/SQLAlchemy when moving to Postgres in production.
"""

from __future__ import annotations

import json
import time
from typing import Any

import aiosqlite

from .config import get_settings


class SignalDB:
    """Async read adapter over ROT's signals table."""

    def __init__(self, db_path: str | None = None) -> None:
        settings = get_settings()
        # Strip SQLAlchemy prefix if present for raw aiosqlite use
        raw = db_path or settings.database_url
        self._path = raw.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._ensure_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def _ensure_schema(self) -> None:
        """Create tables if this is a fresh database (dev/test mode)."""
        assert self._conn
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id      TEXT PRIMARY KEY,
                key_hash    TEXT NOT NULL UNIQUE,
                name        TEXT NOT NULL,
                tier        TEXT NOT NULL DEFAULT 'free',
                created_at  REAL NOT NULL,
                last_used_at REAL
            );

            CREATE TABLE IF NOT EXISTS signals (
                id              TEXT PRIMARY KEY,
                created_at      REAL NOT NULL,
                ticker          TEXT NOT NULL,
                event_type      TEXT NOT NULL DEFAULT 'other',
                stance          TEXT NOT NULL DEFAULT 'unknown',
                time_horizon    TEXT NOT NULL DEFAULT 'unknown',
                confidence      REAL NOT NULL DEFAULT 0.0,
                trend_score     REAL NOT NULL DEFAULT 0.0,
                quality_score   REAL NOT NULL DEFAULT 0.0,
                strategy        TEXT NOT NULL DEFAULT 'none',
                subreddit       TEXT NOT NULL DEFAULT '',
                post_title      TEXT NOT NULL DEFAULT '',
                post_url        TEXT NOT NULL DEFAULT '',
                sector          TEXT,
                ai_summary      TEXT,
                market_data     TEXT,   -- JSON
                reasoning       TEXT,   -- JSON
                trade_idea      TEXT    -- JSON
            );

            CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
            CREATE INDEX IF NOT EXISTS idx_signals_confidence ON signals(confidence DESC);
        """)
        await self._conn.commit()

    # ── Signal queries ────────────────────────────────────────────────────────

    async def count_signals(self) -> int:
        assert self._conn
        async with self._conn.execute("SELECT COUNT(*) FROM signals") as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def get_signals(
        self,
        limit: int = 50,
        offset: int = 0,
        ticker: str | None = None,
        stance: str | None = None,
        min_confidence: float | None = None,
        event_type: str | None = None,
        date_from: float | None = None,
        date_to: float | None = None,
        sort: str = "created_at",
        order: str = "desc",
    ) -> list[dict[str, Any]]:
        assert self._conn

        conditions: list[str] = []
        params: list[Any] = []

        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker.upper())
        if stance:
            conditions.append("stance = ?")
            params.append(stance)
        if min_confidence is not None:
            conditions.append("confidence >= ?")
            params.append(min_confidence)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if date_from is not None:
            conditions.append("created_at >= ?")
            params.append(date_from)
        if date_to is not None:
            conditions.append("created_at <= ?")
            params.append(date_to)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        safe_sort = sort if sort in ("created_at", "confidence", "trend_score") else "created_at"
        safe_order = "ASC" if order.lower() == "asc" else "DESC"

        query = f"""
            SELECT * FROM signals
            {where}
            ORDER BY {safe_sort} {safe_order}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        async with self._conn.execute(query, params) as cur:
            rows = await cur.fetchall()
            return [_row_to_dict(row) for row in rows]

    async def get_signal_by_id(self, signal_id: str) -> dict[str, Any] | None:
        assert self._conn
        async with self._conn.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ) as cur:
            row = await cur.fetchone()
            return _row_to_dict(row) if row else None

    async def get_trending_tickers(
        self, window_hours: int = 24, limit: int = 20
    ) -> list[dict[str, Any]]:
        assert self._conn
        since = time.time() - window_hours * 3600
        query = """
            SELECT
                ticker,
                COUNT(*) AS mention_count,
                SUM(CASE WHEN stance = 'bullish' THEN 1 ELSE 0 END) AS bullish_count,
                SUM(CASE WHEN stance = 'bearish' THEN 1 ELSE 0 END) AS bearish_count,
                AVG(confidence) AS avg_confidence,
                MAX(created_at) AS latest_signal_at,
                AVG(trend_score) AS trend_score
            FROM signals
            WHERE created_at >= ?
            GROUP BY ticker
            ORDER BY mention_count DESC, avg_confidence DESC
            LIMIT ?
        """
        async with self._conn.execute(query, (since, limit)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    # ── API key operations ────────────────────────────────────────────────────

    async def get_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        assert self._conn
        async with self._conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def create_api_key(
        self, key_id: str, key_hash: str, name: str, tier: str
    ) -> None:
        assert self._conn
        await self._conn.execute(
            """INSERT INTO api_keys (key_id, key_hash, name, tier, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (key_id, key_hash, name, tier, time.time()),
        )
        await self._conn.commit()

    async def touch_key(self, key_id: str) -> None:
        assert self._conn
        await self._conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?",
            (time.time(), key_id),
        )
        await self._conn.commit()

    async def list_keys_for_id(self, key_id: str) -> list[dict[str, Any]]:
        assert self._conn
        async with self._conn.execute(
            "SELECT key_id, name, tier, created_at, last_used_at FROM api_keys WHERE key_id = ?",
            (key_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

    # ── Seed helpers (dev / demo) ─────────────────────────────────────────────

    async def seed_demo_signals(self, count: int = 50) -> None:
        """Insert synthetic signals for local development."""
        import random
        import uuid

        tickers = ["AAPL", "TSLA", "NVDA", "SPY", "AMD", "GME", "PLTR", "MSTR"]
        stances = ["bullish", "bearish", "mixed"]
        strategies = ["debit_spread", "credit_spread", "straddle", "none"]
        event_types = ["earnings_rumor", "squeeze_chatter", "product_news", "other"]
        subreddits = ["wallstreetbets", "options", "stocks", "investing"]

        now = time.time()
        rows = []
        for i in range(count):
            ticker = random.choice(tickers)
            created_at = now - random.uniform(0, 86400 * 7)  # last 7 days
            rows.append((
                str(uuid.uuid4()),
                created_at,
                ticker,
                random.choice(event_types),
                random.choice(stances),
                random.choice(["intraday", "1w", "earnings"]),
                round(random.uniform(0.3, 0.95), 3),
                round(random.uniform(0.1, 1.0), 3),
                round(random.uniform(0.4, 0.9), 3),
                random.choice(strategies),
                random.choice(subreddits),
                f"{ticker} looking interesting after earnings beat",
                f"https://reddit.com/r/wallstreetbets/comments/{uuid.uuid4().hex[:6]}",
                random.choice(["Technology", "Finance", "Energy", None]),
                f"AI: {ticker} shows {random.choice(stances)} momentum with {random.randint(50,500)} mentions",
                json.dumps({"price": round(random.uniform(10, 500), 2), "iv_rank": round(random.uniform(0.2, 0.9), 2)}),
                json.dumps({"thesis": f"Community thesis on {ticker}", "invalidations": ["breaks support"]}),
                json.dumps({"strategy": random.choice(strategies), "legs": [], "quality_score": round(random.uniform(0.5, 0.9), 2)}),
            ))

        assert self._conn
        await self._conn.executemany(
            """INSERT OR IGNORE INTO signals
               (id, created_at, ticker, event_type, stance, time_horizon,
                confidence, trend_score, quality_score, strategy, subreddit,
                post_title, post_url, sector, ai_summary, market_data, reasoning, trade_idea)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        await self._conn.commit()


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    for field in ("market_data", "reasoning", "trade_idea"):
        if isinstance(d.get(field), str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, ValueError):
                d[field] = {}
    return d
