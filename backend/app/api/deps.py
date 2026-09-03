"""
Shared FastAPI dependencies for app/api/v1/* routes. Currently just the
auth dependency every protected route uses to resolve the caller's
`user_id` from its bearer token -- see docs/API.md ("Auth").
"""

from fastapi import Header, HTTPException, status

from app.core.security import TokenError, decode_access_token
from app.db import user_repository

_AUTH_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    """
    Every `/api/v1/*` route except `/auth/register` and `/auth/login`
    depends on this. Expects `Authorization: Bearer <token>`; raises 401 for
    a missing header, a malformed scheme, an invalid/expired token, or a
    token whose user no longer exists (the DB round-trip is a deliberate
    boundary check -- see app/services/auth_service.py -- not an
    optimization concern, matching this codebase's no-caching style
    elsewhere).
    """
    if authorization is None:
        raise _AUTH_ERROR
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _AUTH_ERROR
    try:
        user_id = decode_access_token(token)
    except TokenError as exc:
        raise _AUTH_ERROR from exc
    if await user_repository.find_by_id(user_id) is None:
        raise _AUTH_ERROR
    return user_id
