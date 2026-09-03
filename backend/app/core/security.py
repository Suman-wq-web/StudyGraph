"""
Password hashing and JWT issuance/verification for Phase 8 auth. The only
module that imports `bcrypt`/`jose` -- mirrors app/db/mongodb.py being the
only module that imports `motor`, and app/services/rag/embeddings.py /
generation.py being the only modules that import `google.genai`.

Uses the `bcrypt` package directly rather than `passlib` -- passlib's
bcrypt backend is incompatible with modern `bcrypt` releases (>=4.1 dropped
the `__about__` attribute passlib's version probe reads, and its self-test
trips the same 72-byte input limit bcrypt itself enforces), and passlib is
unmaintained upstream. `bcrypt.hashpw`/`checkpw` directly is the current,
dependency-light equivalent.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# bcrypt silently ignores/rejects input past 72 bytes -- see
# app/models/user.py:UserCredentials.password's matching max_length.
_MAX_PASSWORD_BYTES = 72


class TokenError(Exception):
    """Raised for a missing/malformed/expired/invalid-signature token, or a
    server misconfigured with no JWT_SECRET_KEY -- app/api/deps.py turns
    this into a 401."""


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    encoded = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    try:
        return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))
    except ValueError:
        # A malformed stored hash (shouldn't happen -- only hash_password()
        # ever writes one) is a verification failure, not a crash.
        return False


def create_access_token(user_id: str) -> str:
    if not settings.jwt_secret_key:
        raise TokenError("JWT_SECRET_KEY is not configured.")
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str:
    """Returns the user id from a valid token's `sub` claim. Raises
    `TokenError` for anything else (expired, bad signature, malformed,
    missing `sub`, or an unconfigured secret) -- never returns a partial or
    unverified id."""
    if not settings.jwt_secret_key:
        raise TokenError("JWT_SECRET_KEY is not configured.")
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise TokenError("Invalid or expired token.") from exc
    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise TokenError("Token is missing a subject.")
    return user_id
