"""
API key authentication — generate, hash, validate.

Keys are prefixed with `rot_` for instant recognition in user configs.
The raw key is shown once; only its SHA-256 hash is stored.
"""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from typing import Annotated

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from .config import get_settings
from .models import Tier

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

_PAID_TIERS = {Tier.PRO, Tier.PREMIUM, Tier.ULTRA, Tier.ENTERPRISE}


def generate_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        (key_id, raw_key, key_hash)
        Store key_id + key_hash. Return raw_key to user once.
    """
    key_id = str(uuid.uuid4())
    raw = f"rot_{secrets.token_urlsafe(32)}"
    key_hash = _hash_key(raw)
    return key_id, raw, key_hash


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AuthenticatedKey:
    """Resolved API key — attached to request state after validation."""

    def __init__(self, key_id: str, name: str, tier: str) -> None:
        self.key_id = key_id
        self.name = name
        self.tier = Tier(tier)

    @property
    def is_paid(self) -> bool:
        return self.tier in _PAID_TIERS

    @property
    def rpm_limit(self) -> int:
        settings = get_settings()
        mapping = {
            Tier.FREE: settings.free_rpm,
            Tier.PRO: settings.pro_rpm,
            Tier.PREMIUM: settings.pro_rpm,
            Tier.ULTRA: settings.enterprise_rpm,
            Tier.ENTERPRISE: settings.enterprise_rpm,
        }
        return mapping.get(self.tier, settings.free_rpm)

    @property
    def page_limit(self) -> int:
        settings = get_settings()
        if self.tier == Tier.FREE:
            return settings.free_page_limit
        if self.tier in (Tier.ENTERPRISE, Tier.ULTRA):
            return settings.enterprise_page_limit
        return settings.pro_page_limit

    @property
    def delay_seconds(self) -> int:
        return 0 if self.is_paid else get_settings().free_delay_seconds


async def resolve_api_key(
    raw_key: Annotated[str | None, Security(API_KEY_HEADER)],
    request: "Request",
) -> AuthenticatedKey:
    """Validate the X-API-Key header and return the resolved key object."""
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header. Get a free key at https://github.com/Mattbusel/rot-signals-api",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    db = request.app.state.db
    key_hash = _hash_key(raw_key)
    record = await db.get_key_by_hash(key_hash)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    await db.touch_key(record["key_id"])
    return AuthenticatedKey(
        key_id=record["key_id"],
        name=record["name"],
        tier=record["tier"],
    )
