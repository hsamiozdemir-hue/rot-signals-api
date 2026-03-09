"""
Per-key rate limiting middleware using slowapi + in-memory state.

For production, swap the in-memory store for Redis via slowapi's
Redis backend or a custom limiter.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.auth import _hash_key
from core.config import get_settings

# key_hash → deque of request timestamps (sliding window)
_windows: dict[str, deque[float]] = {}

_SKIP_PATHS = {"/v1/health", "/docs", "/openapi.json", "/redoc"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter keyed by API key hash.

    Returns 429 with Retry-After header when limit is exceeded.
    Injects X-RateLimit-* headers on every response.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        raw_key = request.headers.get("X-API-Key") or request.query_params.get("api_key", "")
        if not raw_key:
            return await call_next(request)

        settings = get_settings()
        key_hash = _hash_key(raw_key)
        now = time.time()
        window = 60.0  # 1-minute sliding window

        bucket = _windows.setdefault(key_hash, deque())
        # Evict old entries
        while bucket and now - bucket[0] > window:
            bucket.popleft()

        # Determine limit from DB-resolved tier if available, else use free default
        rpm = settings.free_rpm
        db = getattr(request.app.state, "db", None)
        if db is not None:
            record = await db.get_key_by_hash(key_hash)
            if record:
                from core.auth import AuthenticatedKey
                k = AuthenticatedKey(record["key_id"], record["name"], record["tier"])
                rpm = k.rpm_limit

        remaining = max(0, rpm - len(bucket))
        reset_at = int(bucket[0] + window) if bucket else int(now + window)

        response_headers: dict[str, str] = {
            "X-RateLimit-Limit": str(rpm),
            "X-RateLimit-Remaining": str(max(0, remaining - 1)),
            "X-RateLimit-Reset": str(reset_at),
        }

        if len(bucket) >= rpm:
            retry_after = max(1, reset_at - int(now))
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. {rpm} requests/minute on your tier.",
                    "retry_after_s": retry_after,
                },
                headers={**response_headers, "Retry-After": str(retry_after)},
            )

        bucket.append(now)
        response = await call_next(request)
        for k, v in response_headers.items():
            response.headers[k] = v
        return response
