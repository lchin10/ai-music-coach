"""Who is calling, and do they own what they're asking about.

The backend talks to Supabase with the service-role key, which bypasses RLS.
So identity comes from the caller's Supabase access token, never from a
user_id in the request, and every resource id is checked against it.
"""

import time
import uuid
from typing import Optional

from fastapi import Header, HTTPException

from app import db

CACHE_SECONDS = 60
_verified: dict = {}  # token -> (user_id, checked_at)


def current_user(authorization: Optional[str] = Header(None)) -> str:
    """FastAPI dependency: the verified user id, or 401."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Missing bearer token")

    hit = _verified.get(token)
    if hit and time.monotonic() - hit[1] < CACHE_SECONDS:
        return hit[0]

    client = db.client()
    if client is None:
        raise HTTPException(503, "Auth unavailable")
    try:
        # ponytail: one Auth round trip per token per minute; verify the JWT
        # locally against the project's JWKS (PyJWT) if that latency shows up.
        user = client.auth.get_user(token).user
    except Exception:
        user = None
    if not user:
        raise HTTPException(401, "Invalid or expired token")

    if len(_verified) > 1000:
        _verified.clear()
    _verified[token] = (user.id, time.monotonic())
    return user.id


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except ValueError:
        return False


def own_piece(user_id: str, piece_id: str) -> dict:
    """The caller's piece row, or 404 — never 403, which would confirm it exists."""
    if _is_uuid(piece_id):
        rows = (
            db.client().table("pieces").select("*")
            .eq("id", piece_id).eq("user_id", user_id).limit(1).execute()
        ).data
        if rows:
            return rows[0]
    raise HTTPException(404, "Piece not found")


def own_session(user_id: str, session_id: str, piece_id: Optional[str] = None) -> dict:
    """The caller's practice session (on `piece_id`, when given), or 404."""
    if _is_uuid(session_id):
        query = (
            db.client().table("practice_sessions").select("*")
            .eq("id", session_id).eq("user_id", user_id)
        )
        if piece_id is not None:
            query = query.eq("piece_id", piece_id)
        rows = query.limit(1).execute().data
        if rows:
            return rows[0]
    raise HTTPException(404, "Session not found")
