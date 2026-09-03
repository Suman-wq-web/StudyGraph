"""
Business logic for registration/login/`/me`. Routes in app/api/v1/auth.py
call into this module rather than touching app/db or app/core/security
directly, matching resource_service.py's role for resources.
"""

from app.core.google_auth import GoogleAuthError, verify_google_id_token
from app.core.security import create_access_token, hash_password, verify_password
from app.db import user_repository
from app.models.user import Token, UserCredentials, UserPublic, UserUpdate

# Re-exported so app/api/v1/auth.py only ever imports from this module, not
# app/core/google_auth directly -- matching resource_service.py's role of
# being the sole boundary its routes go through.
__all__ = [
    "GoogleAuthError",
    "InvalidCredentialsError",
    "get_current_user",
    "login",
    "login_with_google",
    "register",
    "update_profile",
]


class InvalidCredentialsError(Exception):
    """Raised on login with an unknown email, a wrong password, or an
    account that has no password at all (Google-only) -- routes map all
    three to the same 401 so a caller can't enumerate registered emails or
    sign-in methods by timing/response-shape differences."""


def _to_public(user) -> UserPublic:
    return UserPublic(id=user.id, email=user.email, name=user.name, created_at=user.created_at)


async def register(credentials: UserCredentials) -> UserPublic:
    user = await user_repository.create(
        email=credentials.email, hashed_password=hash_password(credentials.password)
    )
    return _to_public(user)


async def login(credentials: UserCredentials) -> Token:
    user = await user_repository.find_by_email(credentials.email)
    if (
        user is None
        or user.hashed_password is None
        or not verify_password(credentials.password, user.hashed_password)
    ):
        raise InvalidCredentialsError()
    return Token(access_token=create_access_token(user.id))


async def login_with_google(credential: str) -> Token:
    """Verifies a Google Identity Services ID token, finds-or-creates the
    matching StudyGraph user, and issues the same kind of access token
    `login`/`register` do. A brand-new email creates a new Google-only
    account; a repeat login with the same previously-linked google_id logs
    into the existing one. Raises GoogleAuthError -- app/api/v1/auth.py maps
    this to a generic 401 -- for an invalid/unverified credential, or for an
    email that belongs to an existing account not already linked to this
    exact google_id (a password-only account, or one linked to a different
    google_id): a matching email alone never links or logs into an account
    the caller hasn't already proven they own, see
    app/db/user_repository.py:find_or_create_google_user."""
    identity = verify_google_id_token(credential)
    try:
        user = await user_repository.find_or_create_google_user(
            email=identity.email, name=identity.name, google_id=identity.subject
        )
    except user_repository.GoogleAccountConflictError as exc:
        raise GoogleAuthError("Invalid Google credential.") from exc
    return Token(access_token=create_access_token(user.id))


async def get_current_user(user_id: str) -> UserPublic | None:
    user = await user_repository.find_by_id(user_id)
    if user is None:
        return None
    return _to_public(user)


async def update_profile(user_id: str, payload: UserUpdate) -> UserPublic | None:
    user = await user_repository.update(user_id, name=payload.name)
    if user is None:
        return None
    return _to_public(user)
