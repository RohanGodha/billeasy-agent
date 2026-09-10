"""Auth router. Only one endpoint: verify the shared password."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.auth.middleware import verify_password
from app.auth.throttle import (
    MAX_FAILURES,
    is_locked,
    register_failure,
    reset,
    retry_after_seconds,
)
from app.observability import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class VerifyIn(BaseModel):
    password: str


class VerifyOut(BaseModel):
    ok: bool
    token: str


def _client_key(request: Request) -> str:
    """Best-effort client identity for throttling.

    Behind Render/Vercel the peer address is the proxy, so the first hop in
    X-Forwarded-For is used when present. It is spoofable by a direct caller, which is
    why this is a brute-force speed bump and not an access control.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post(
    "/verify",
    response_model=VerifyOut,
    summary="Exchange the shared password for an access token",
)
async def verify(body: VerifyIn, request: Request) -> VerifyOut:
    client = _client_key(request)

    if is_locked(client):
        retry_after = retry_after_seconds(client)
        logger.warning("Auth lockout for %s (%d failures)", client, MAX_FAILURES)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    if not verify_password(body.password):
        count = register_failure(client)
        logger.warning("Failed auth attempt %d/%d from %s", count, MAX_FAILURES, client)
        raise HTTPException(status_code=401, detail="Invalid password")

    reset(client)
    # Token == password (single shared-key model). The UI stores it and sends it as
    # X-Access-Token. Replacing this with per-user JWT + refresh is the first thing
    # that changes for production — see README §12.
    return VerifyOut(ok=True, token=body.password)
