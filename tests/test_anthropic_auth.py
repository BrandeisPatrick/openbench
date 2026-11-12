"""Credential resolution for Anthropic calls: API key > auth token > ant login."""

from __future__ import annotations

import httpx
import pytest

from openbench import anthropic_auth
from openbench.runners.protocols import providers


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)


def _ant(monkeypatch, tokens):
    """Make ant_access_token() return successive values from `tokens`."""
    it = iter(tokens)
    calls = []

    def fake():
        calls.append(1)
        return next(it)

    monkeypatch.setattr(anthropic_auth, "ant_access_token", fake)
    return calls


def _sent_headers(client: httpx.Client, status_codes=(200,)) -> list[httpx.Headers]:
    seen: list[httpx.Headers] = []
    codes = iter(status_codes)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(httpx.Headers(request.headers))  # copy: the retry mutates it
        return httpx.Response(next(codes), json={})

    client._transport = httpx.MockTransport(handler)
    client.post("https://api.anthropic.com/v1/messages", json={})
    return seen


def test_api_key_wins(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-1")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-env")
    calls = _ant(monkeypatch, ["tok-ant"])
    (headers,) = _sent_headers(anthropic_auth.make_client(5))
    assert headers["x-api-key"] == "key-1"
    assert "authorization" not in headers
    assert "anthropic-beta" not in headers
    assert calls == []
    assert anthropic_auth.source() == "api-key"


def test_auth_token_env_beats_ant(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok-env")
    calls = _ant(monkeypatch, ["tok-ant"])
    (headers,) = _sent_headers(anthropic_auth.make_client(5))
    assert headers["authorization"] == "Bearer tok-env"
    assert headers["anthropic-beta"] == "oauth-2025-04-20"
    assert "x-api-key" not in headers
    assert calls == []


def test_ant_login_fallback(monkeypatch):
    _ant(monkeypatch, ["tok-ant"])
    (headers,) = _sent_headers(anthropic_auth.make_client(5))
    assert headers["authorization"] == "Bearer tok-ant"
    assert headers["anthropic-beta"] == "oauth-2025-04-20"
    assert headers["anthropic-version"] == anthropic_auth.ANTHROPIC_VERSION


def test_ant_login_refetches_on_401(monkeypatch):
    _ant(monkeypatch, ["tok-old", "tok-new"])
    first, second = _sent_headers(anthropic_auth.make_client(5), status_codes=(401, 200))
    assert first["authorization"] == "Bearer tok-old"
    assert second["authorization"] == "Bearer tok-new"
    assert second["anthropic-beta"] == "oauth-2025-04-20"


def test_ant_login_refetches_when_stale(monkeypatch):
    _ant(monkeypatch, ["tok-new"])
    auth = anthropic_auth.AntLoginAuth("tok-old")
    assert auth._current() == "tok-old"
    auth._fetched_at -= anthropic_auth._TOKEN_TTL_S + 1
    assert auth._current() == "tok-new"


def test_keeps_old_token_if_ant_disappears(monkeypatch):
    _ant(monkeypatch, [None])
    auth = anthropic_auth.AntLoginAuth("tok-old")
    assert auth._current(force=True) == "tok-old"


def test_no_credentials_raises(monkeypatch):
    _ant(monkeypatch, [None, None])
    with pytest.raises(RuntimeError, match="ant auth login"):
        anthropic_auth.make_client(5, purpose="for model claude-x")
    assert anthropic_auth.source() is None


def test_ant_access_token_rejects_foreign_binary(monkeypatch):
    class Proc:
        returncode = 0
        stdout = "Apache Ant(TM) version 1.10\n"

    monkeypatch.setattr(anthropic_auth.shutil, "which", lambda _: "/usr/bin/ant")
    monkeypatch.setattr(anthropic_auth.subprocess, "run", lambda *a, **k: Proc())
    assert anthropic_auth.ant_access_token() is None
    Proc.stdout = "tok-123\n"
    assert anthropic_auth.ant_access_token() == "tok-123"
    monkeypatch.setattr(anthropic_auth.shutil, "which", lambda _: None)
    assert anthropic_auth.ant_access_token() is None


def test_openai_compat_claude_route_uses_bearer_fallback(monkeypatch):
    _ant(monkeypatch, ["tok-ant"])
    base_url, key, wire = providers._resolve_provider("claude-opus-4-8")
    assert (key, wire) == ("tok-ant", "claude-opus-4-8")


def test_other_providers_do_not_fall_back(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = _ant(monkeypatch, ["tok-ant"])
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        providers._resolve_provider("gpt-5.5")
    assert calls == []
