"""Tests for API key generation and authentication."""

from __future__ import annotations

import pytest

from core.auth import AuthenticatedKey, _hash_key, generate_key
from core.models import Tier


def test_generate_key_has_rot_prefix():
    _, raw, _ = generate_key()
    assert raw.startswith("rot_")


def test_generate_key_hash_differs_from_raw():
    _, raw, key_hash = generate_key()
    assert raw != key_hash


def test_generate_key_same_raw_same_hash():
    _, raw, key_hash = generate_key()
    assert _hash_key(raw) == key_hash


def test_generate_key_unique():
    _, raw1, _ = generate_key()
    _, raw2, _ = generate_key()
    assert raw1 != raw2


def test_authenticated_key_free_is_not_paid():
    key = AuthenticatedKey("id", "name", "free")
    assert not key.is_paid


def test_authenticated_key_pro_is_paid():
    key = AuthenticatedKey("id", "name", "pro")
    assert key.is_paid


def test_authenticated_key_enterprise_is_paid():
    key = AuthenticatedKey("id", "name", "enterprise")
    assert key.is_paid


def test_free_key_has_delay():
    key = AuthenticatedKey("id", "name", "free")
    assert key.delay_seconds > 0


def test_pro_key_no_delay():
    key = AuthenticatedKey("id", "name", "pro")
    assert key.delay_seconds == 0


def test_free_key_rpm_less_than_pro():
    free = AuthenticatedKey("id", "name", "free")
    pro = AuthenticatedKey("id", "name", "pro")
    assert free.rpm_limit < pro.rpm_limit


def test_free_key_page_limit_less_than_pro():
    free = AuthenticatedKey("id", "name", "free")
    pro = AuthenticatedKey("id", "name", "pro")
    assert free.page_limit < pro.page_limit
