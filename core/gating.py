"""
Tier gating — applies free/paid restrictions to signal data.

Mirrors the logic in ROT's tier_gate.py but operates on
the API's Pydantic models rather than raw dicts.
"""

from __future__ import annotations

import time
from typing import Any

from .auth import AuthenticatedKey
from .models import Reasoning, Signal, TradeIdea


_LOCKED_REASONING = Reasoning(
    **{
        "_locked": True,
        "_upgrade_message": "Upgrade to Pro for real-time signals with full reasoning. "
                            "See https://github.com/Mattbusel/rot-signals-api#pricing",
    }
)

_LOCKED_TRADE_IDEA_BASE: dict[str, Any] = {
    "_locked": True,
    "_upgrade_message": "Upgrade to Pro for trade ideas and option legs.",
}


def gate(raw: dict[str, Any], key: AuthenticatedKey) -> dict[str, Any]:
    """
    Apply tier gating to a raw signal dict before model validation.

    Modifies and returns a shallow copy.
    """
    if key.is_paid:
        return raw

    out = dict(raw)
    created_at = float(raw.get("created_at", 0))
    age = time.time() - created_at

    if age < key.delay_seconds:
        # Signal is too fresh — redact everything and attach delay metadata
        out["_delayed"] = True
        out["_available_in_s"] = int(key.delay_seconds - age)
        out["reasoning"] = {"_locked": True, "_upgrade_message": "Signal not yet available on free tier."}
        out["trade_idea"] = {
            "strategy": raw.get("strategy", "none"),
            "legs": [],
            "_locked": True,
            "_upgrade_message": "Real-time signals require Pro tier.",
        }
        # Redact high-signal fields
        out["ai_summary"] = None
        return out

    # Delayed signal: show basic fields, redact reasoning and legs
    out["reasoning"] = {"_locked": True, "_upgrade_message": "Full reasoning requires Pro tier."}
    trade = dict(raw.get("trade_idea") or {})
    trade["legs"] = []
    trade["_locked"] = True
    trade["_upgrade_message"] = "Option legs require Pro tier."
    out["trade_idea"] = trade
    out["ai_summary"] = None
    return out


def gate_list(raws: list[dict[str, Any]], key: AuthenticatedKey) -> list[dict[str, Any]]:
    limited = raws[: key.page_limit]
    return [gate(r, key) for r in limited]
