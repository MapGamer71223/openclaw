"""
Auth for the narrow /agent/* tool surface that an external OpenClaw agent
calls into. If OPENCLAW_API_TOKEN is configured, every /agent/* call must
present it as a Bearer token. If it's not configured (local-dev default),
the endpoints are open -- fine on localhost, not fine on anything else.

This never touches or exposes GEMINI_API_KEY / BRAVE_API_KEY / XAI_API_KEY /
.env contents; it only gates the backend's own tool endpoints.
"""
import hmac

from fastapi import Header, HTTPException


def require_agent_token(authorization: str = Header(default=None)) -> None:
    from app.config import settings

    if not settings.OPENCLAW_API_TOKEN:
        return  # auth disabled -- local dev only, documented in OPENCLAW_INTEGRATION.md

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token for agent endpoint.")

    presented = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(presented, settings.OPENCLAW_API_TOKEN):
        raise HTTPException(401, "Invalid agent token.")
