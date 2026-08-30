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


def ws_auth(ws) -> tuple[bool, str | None]:
    """用 WebSocket 子协议传递 token，避免出现在 URL 与访问日志中。

    客户端约定发送 ["geass", <token>]，服务端据此校验并回选 "geass" 子协议。
    """
    state = ws.app.state.geass
    header = ws.headers.get("sec-websocket-protocol", "")
    parts = [part.strip() for part in header.split(",") if part.strip()]
    if (
        len(parts) >= 2
        and parts[0] == "geass"
        and token_matches(state.config.server.token, parts[1])
    ):
        return True, "geass"
    if parts and token_matches(state.config.server.token, parts[0]):
        return True, parts[0]
    return False, None
