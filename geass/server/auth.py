"""Token 校验。"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request


def token_matches(expected: str, provided: str | None) -> bool:
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)


async def require_token(
    request: Request,
    x_geass_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    state = request.app.state.geass
    token = x_geass_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if not token_matches(state.config.server.token, token):
        raise HTTPException(status_code=401, detail="invalid token")
    return token or ""

