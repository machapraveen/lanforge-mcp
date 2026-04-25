"""Smoke tests for env-driven Settings parsing."""

from __future__ import annotations

import pytest

from lanforge_mcp.config import Settings, _env_bool, _env_int


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("On", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("Off", False),
        ("garbage", True),
        ("", True),
    ],
)
def test_env_bool(monkeypatch: pytest.MonkeyPatch, value: str, expected: bool) -> None:
    monkeypatch.setenv("XYZ", value)
    assert _env_bool("XYZ", True) is expected


def test_env_bool_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XYZ", raising=False)
    assert _env_bool("XYZ", False) is False


def test_env_int_unparseable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XYZ", "not-a-number")
    assert _env_int("XYZ", 42) == 42


def test_settings_from_env_uses_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANFORGE_HOST", "10.0.0.5")
    monkeypatch.setenv("LANFORGE_PORT", "9090")
    monkeypatch.setenv("LANFORGE_MOCK", "0")
    monkeypatch.setenv("LANFORGE_TIMEOUT_SEC", "20")
    s = Settings.from_env()
    assert s.host == "10.0.0.5"
    assert s.port == 9090
    assert s.mock is False
    assert s.timeout_sec == 20
    assert s.base_url == "http://10.0.0.5:9090"


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("LANFORGE_HOST", "LANFORGE_PORT", "LANFORGE_MOCK", "LANFORGE_TIMEOUT_SEC"):
        monkeypatch.delenv(k, raising=False)
    s = Settings.from_env()
    assert s.host == "localhost"
    assert s.port == 8080
    assert s.mock is True
    assert s.timeout_sec == 10
