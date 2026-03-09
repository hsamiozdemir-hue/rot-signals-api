"""Tests for tier-based signal gating."""

from __future__ import annotations

import time

import pytest

from core.auth import AuthenticatedKey
from core.gating import gate, gate_list
from tests.conftest import make_signal_row


def _free_key() -> AuthenticatedKey:
    return AuthenticatedKey("id", "test", "free")


def _pro_key() -> AuthenticatedKey:
    return AuthenticatedKey("id", "test", "pro")


def test_pro_key_gets_full_signal():
    row = make_signal_row(age_seconds=0)
    result = gate(row, _pro_key())
    assert result.get("reasoning") is not None
    assert isinstance(result["reasoning"], dict)
    assert result["trade_idea"].get("legs") is not None


def test_free_key_fresh_signal_is_delayed():
    row = make_signal_row(age_seconds=0)  # just created
    result = gate(row, _free_key())
    assert result.get("_delayed") is True
    assert result.get("_available_in_s", 0) > 0


def test_free_key_fresh_signal_redacts_reasoning():
    row = make_signal_row(age_seconds=0)
    result = gate(row, _free_key())
    reasoning = result.get("reasoning", {})
    assert reasoning.get("_locked") is True


def test_free_key_fresh_signal_redacts_legs():
    row = make_signal_row(age_seconds=0)
    result = gate(row, _free_key())
    legs = result.get("trade_idea", {}).get("legs", [])
    assert legs == []


def test_free_key_old_signal_not_delayed():
    row = make_signal_row(age_seconds=1800)  # 30 min old, past 15-min delay
    result = gate(row, _free_key())
    assert not result.get("_delayed", False)


def test_free_key_old_signal_still_locks_reasoning():
    row = make_signal_row(age_seconds=1800)
    result = gate(row, _free_key())
    reasoning = result.get("reasoning", {})
    assert reasoning.get("_locked") is True


def test_free_key_old_signal_still_locks_legs():
    row = make_signal_row(age_seconds=1800)
    result = gate(row, _free_key())
    legs = result.get("trade_idea", {}).get("legs", [])
    assert legs == []


def test_gate_list_limits_free_page_size():
    rows = [make_signal_row(age_seconds=1800) for _ in range(50)]
    key = _free_key()
    result = gate_list(rows, key)
    assert len(result) <= key.page_limit


def test_gate_list_pro_returns_all():
    rows = [make_signal_row(age_seconds=0) for _ in range(30)]
    result = gate_list(rows, _pro_key())
    assert len(result) == 30


def test_gate_preserves_ticker_and_stance():
    row = make_signal_row(ticker="TSLA", stance="bearish", age_seconds=1800)
    result = gate(row, _free_key())
    assert result["ticker"] == "TSLA"
    assert result["stance"] == "bearish"
