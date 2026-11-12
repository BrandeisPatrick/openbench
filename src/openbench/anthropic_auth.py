"""Anthropic credentials for host-side API calls.

Resolution order, first hit wins:

1. ``ANTHROPIC_API_KEY``    -> ``x-api-key`` header (a Console API key).
2. ``ANTHROPIC_AUTH_TOKEN`` -> ``Authorization: Bearer`` (a static OAuth token,
   e.g. from ``ant auth print-credentials --env``).
3. the ``ant`` CLI login   -> ``Authorization: Bearer``, token fetched with
   ``ant auth print-credentials --access-token``. ``ant`` refreshes a token
   that is expired or near expiry, so we re-ask it every few minutes and a
   long matrix outlives the token's lifetime.

The token is only ever used from the host process. It is never passed into a
sandbox container (see runners/execute.py).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Generator

import httpx

ANTHROPIC_VERSION = "2023-06-01"
# Required with an OAuth Bearer token on raw HTTP (both Bearer paths below);
# never sent with an API key.
OAUTH_BETA = "oauth-2025-04-20"
# Re-ask `ant` this often. Cheap (a local file read unless a refresh is due)
# and far below any token lifetime.
_TOKEN_TTL_S = 300.0
_ANT_TIMEOUT_S = 30

_NO_CREDENTIALS = (
    "no Anthropic credentials: set ANTHROPIC_API_KEY, or ANTHROPIC_AUTH_TOKEN, "
    "or log in with `ant auth login`"
)


def ant_access_token() -> str | None:
    """The `ant` CLI's current access token, or None if ant is missing or logged out."""
    exe = shutil.which("ant")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "auth", "print-credentials", "--access-token"],
            capture_output=True,
            text=True,
            timeout=_ANT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    token = proc.stdout.strip()
    # Guard against a same-named binary (e.g. Apache Ant) printing something else.
    if proc.returncode != 0 or not token or any(c.isspace() for c in token):
        return None
    return token


def bearer_token() -> str | None:
    """A Bearer token from the environment or the ant login (no API-key lookup)."""
    return os.environ.get("ANTHROPIC_AUTH_TOKEN") or ant_access_token()


def source() -> str | None:
    """Which credential would be used: 'api-key' | 'auth-token' | 'ant-login' | None."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api-key"
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "auth-token"
    if ant_access_token():
        return "ant-login"
    return None


class AntLoginAuth(httpx.Auth):
    """Bearer auth backed by the ant CLI; re-fetches the token as it ages or on a 401."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token
        self._fetched_at = time.monotonic() if token else 0.0

    def _current(self, force: bool = False) -> str:
        stale = time.monotonic() - self._fetched_at > _TOKEN_TTL_S
        if force or stale or not self._token:
            fresh = ant_access_token()
            if fresh:
                self._token, self._fetched_at = fresh, time.monotonic()
            elif not self._token:
                raise RuntimeError(_NO_CREDENTIALS)
        return self._token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self._current()}"
        response = yield request
        if response.status_code == 401:
            request.headers["Authorization"] = f"Bearer {self._current(force=True)}"
            yield request


def make_client(timeout: float, purpose: str = "") -> httpx.Client:
    """An httpx client for api.anthropic.com authenticated per the order above."""
    headers = {"anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return httpx.Client(headers={**headers, "x-api-key": key}, timeout=timeout)
    if token := os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return httpx.Client(
            headers={**headers, "Authorization": f"Bearer {token}", "anthropic-beta": OAUTH_BETA},
            timeout=timeout,
        )
    if token := ant_access_token():
        return httpx.Client(
            headers={**headers, "anthropic-beta": OAUTH_BETA},
            auth=AntLoginAuth(token),
            timeout=timeout,
        )
    raise RuntimeError(_NO_CREDENTIALS + (f" (required {purpose})" if purpose else ""))
