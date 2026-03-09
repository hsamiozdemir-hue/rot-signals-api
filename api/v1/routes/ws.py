"""
WebSocket endpoint — real-time signal stream.

WS /v1/ws/signals?api_key=rot_...

Free tier  : delayed signals only (15-min lag), 1 concurrent connection max.
Pro+       : real-time, up to 5 concurrent connections, filter by ticker/stance.

Protocol
--------
Client → Server:
  {"type": "subscribe",   "data": {"tickers": ["AAPL"], "min_confidence": 0.7}}
  {"type": "unsubscribe", "data": {"tickers": ["AAPL"]}}

Server → Client:
  {"type": "signal",    "data": <Signal object>, "ts": <unix float>}
  {"type": "heartbeat", "data": null,             "ts": <unix float>}
  {"type": "error",     "data": {"message": "..."}, "ts": <unix float>}
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from core.auth import AuthenticatedKey, _hash_key
from core.config import get_settings
from core.gating import gate
from core.models import WSMessage, WSMessageType, WSSubscribePayload

router = APIRouter(tags=["websocket"])

# Simple in-memory broadcast bus — replace with Redis pub/sub for multi-worker
_subscribers: dict[str, "Connection"] = {}


class Connection:
    def __init__(self, ws: WebSocket, key: AuthenticatedKey) -> None:
        self.ws = ws
        self.key = key
        self.tickers: set[str] = set()
        self.min_confidence: float = 0.0
        self.stances: set[str] = set()

    def matches(self, signal: dict[str, Any]) -> bool:
        if self.tickers and signal.get("ticker") not in self.tickers:
            return False
        if signal.get("confidence", 0) < self.min_confidence:
            return False
        if self.stances and signal.get("stance") not in self.stances:
            return False
        return True

    async def send(self, msg: dict[str, Any]) -> None:
        await self.ws.send_text(json.dumps(msg))


async def broadcast_signal(signal: dict[str, Any]) -> None:
    """Called by the ROT ingest pipeline whenever a new signal is ready."""
    dead: list[str] = []
    for conn_id, conn in list(_subscribers.items()):
        if not conn.matches(signal):
            continue
        gated = gate(signal, conn.key)
        try:
            await conn.send({
                "type": WSMessageType.SIGNAL.value,
                "data": gated,
                "ts": time.time(),
            })
        except Exception:
            dead.append(conn_id)
    for conn_id in dead:
        _subscribers.pop(conn_id, None)


@router.websocket("/ws/signals")
async def ws_signals(websocket: WebSocket, api_key: str = "") -> None:
    """
    Real-time signal WebSocket.

    Authenticate via query param: `?api_key=rot_...`
    """
    settings = get_settings()
    db = websocket.app.state.db

    # Validate key
    if not api_key:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing api_key")
        return

    key_hash = _hash_key(api_key)
    record = await db.get_key_by_hash(key_hash)
    if not record:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid api_key")
        return

    key = AuthenticatedKey(
        key_id=record["key_id"],
        name=record["name"],
        tier=record["tier"],
    )

    # Enforce concurrent connection limits
    user_conns = sum(1 for c in _subscribers.values() if c.key.key_id == key.key_id)
    max_conns = (
        settings.ws_max_connections_pro if key.is_paid
        else settings.ws_max_connections_free
    )
    if user_conns >= max_conns:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason=f"Max concurrent connections ({max_conns}) reached for your tier.",
        )
        return

    await websocket.accept()
    conn_id = f"{key.key_id}:{time.time()}"
    conn = Connection(ws=websocket, key=key)
    _subscribers[conn_id] = conn

    await conn.send({
        "type": WSMessageType.HEARTBEAT.value,
        "data": {
            "tier": key.tier.value,
            "delay_seconds": key.delay_seconds,
            "message": "Connected to ROT Signals stream. "
                       + ("Real-time feed active." if key.is_paid else
                          f"Free tier: signals delayed by {key.delay_seconds // 60} minutes."),
        },
        "ts": time.time(),
    })

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(settings.ws_ping_interval)
            try:
                await conn.send({"type": WSMessageType.HEARTBEAT.value, "data": None, "ts": time.time()})
            except Exception:
                break

    heartbeat_task = asyncio.create_task(_heartbeat())

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = WSMessage.model_validate_json(raw)
            except Exception:
                await conn.send({
                    "type": WSMessageType.ERROR.value,
                    "data": {"message": "Invalid message format. Expected JSON with 'type' field."},
                    "ts": time.time(),
                })
                continue

            if msg.type == WSMessageType.SUBSCRIBE:
                try:
                    payload = WSSubscribePayload.model_validate(msg.data or {})
                    if payload.tickers:
                        conn.tickers.update(t.upper() for t in payload.tickers)
                    conn.min_confidence = max(conn.min_confidence, payload.min_confidence)
                    if payload.stances:
                        conn.stances.update(s.value for s in payload.stances)
                except Exception as e:
                    await conn.send({
                        "type": WSMessageType.ERROR.value,
                        "data": {"message": str(e)},
                        "ts": time.time(),
                    })

            elif msg.type == WSMessageType.UNSUBSCRIBE:
                try:
                    payload = WSSubscribePayload.model_validate(msg.data or {})
                    for t in payload.tickers:
                        conn.tickers.discard(t.upper())
                except Exception:
                    pass

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        _subscribers.pop(conn_id, None)
