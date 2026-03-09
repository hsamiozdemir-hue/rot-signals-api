"""
POST /v1/keys       — create an API key
GET  /v1/keys/me    — info about current key
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from core.auth import AuthenticatedKey, generate_key, resolve_api_key
from core.config import get_settings
from core.models import APIKeyCreate, APIKeyInfo, APIKeyResponse, Tier

router = APIRouter(prefix="/keys", tags=["auth"])


def _db(request: Request):  # type: ignore[return]
    return request.app.state.db


@router.post("", response_model=APIKeyResponse, status_code=201, summary="Create API key")
async def create_key(
    payload: APIKeyCreate,
    request: Request,
    db=Depends(_db),
) -> APIKeyResponse:
    """
    Generate a new API key.

    The raw key is **shown exactly once** — store it securely.
    Keys cannot be retrieved after creation; delete and recreate if lost.

    Free tier keys are created immediately. Paid tiers require Stripe setup
    (see `/docs#section/Pricing`).
    """
    settings = get_settings()
    # Paid tier creation would validate Stripe subscription here
    tier = Tier.FREE if payload.tier == Tier.FREE else Tier.FREE  # non-free requires billing

    key_id, raw_key, key_hash = generate_key()
    await db.create_api_key(key_id=key_id, key_hash=key_hash, name=payload.name, tier=tier.value)

    rpm = {
        Tier.FREE: settings.free_rpm,
        Tier.PRO: settings.pro_rpm,
        Tier.ENTERPRISE: settings.enterprise_rpm,
    }.get(tier, settings.free_rpm)

    return APIKeyResponse(
        key=raw_key,
        key_id=key_id,
        name=payload.name,
        tier=tier,
        created_at=time.time(),
        rpm_limit=rpm,
    )


@router.get("/me", response_model=APIKeyInfo, summary="Current key info")
async def key_info(
    key: AuthenticatedKey = Depends(resolve_api_key),
    db=Depends(_db),
) -> APIKeyInfo:
    """Return metadata about the authenticated API key (never the key itself)."""
    rows = await db.list_keys_for_id(key.key_id)
    if not rows:
        return APIKeyInfo(
            key_id=key.key_id,
            name=key.name,
            tier=key.tier,
            created_at=time.time(),
            last_used_at=None,
            rpm_limit=key.rpm_limit,
        )
    row = rows[0]
    return APIKeyInfo(
        key_id=key.key_id,
        name=row["name"],
        tier=key.tier,
        created_at=row["created_at"],
        last_used_at=row.get("last_used_at"),
        rpm_limit=key.rpm_limit,
    )
