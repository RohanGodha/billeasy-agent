"""Shared-password gate.

Clients send the password in the `X-Access-Token` header. Comparison is constant-time.
No JWT, no sessions — the password is the bearer.

The header is the only accepted transport. A `?token=` query parameter used to be
allowed for browsers' native `EventSource`, which cannot set headers — but query strings
land in proxy logs, browser history and Referer headers, which is a poor place for a
credential. The UI streams with `@microsoft/fetch-event-source`, which does set headers,
so the query-param path was removed rather than kept for a client we don't use.
"""
from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status

from app.settings import Settings, get_settings


def verify_password(provided: str, settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    if not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), s.app_password.encode("utf-8"))


async def require_token(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency. Raises 401 if the password is missing or wrong."""
    token = request.headers.get("x-access-token") or ""
    if not verify_password(token, settings):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing access token.",
        )
