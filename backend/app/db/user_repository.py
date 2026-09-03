"""
Persistence for the `users` collection (Phase 8). Mirrors
resource_repository.py's pattern -- the only module that turns User data
into Mongo documents and back.
"""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from app.db import mongodb
from app.db.collections import USERS
from app.models.user import User


class EmailAlreadyRegisteredError(Exception):
    """Raised by create() when the (already-lowercased) email is taken."""


class GoogleAccountConflictError(Exception):
    """Raised by find_or_create_google_user() when a verified Google
    identity's email belongs to an existing account that is NOT already
    linked to that same google_id -- a password-only account with no
    google_id yet, or one linked to a different google_id. A matching email
    is never, by itself, treated as proof that the caller already owns that
    account; find_or_create_google_user never links/overwrites in this case
    (see app/services/auth_service.py:login_with_google, which maps this to
    the same generic 401 as an invalid token)."""


def _get_collection():
    return mongodb.get_database()[USERS]


def _to_object_id(user_id: str) -> ObjectId | None:
    try:
        return ObjectId(user_id)
    except (InvalidId, TypeError):
        return None


def _doc_to_user(doc: dict[str, Any]) -> User:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return User.model_validate(doc)


async def create(*, email: str, hashed_password: str) -> User:
    """`email` must already be normalized (lowercased/stripped) by the
    caller -- see app/models/user.py:UserCredentials. Raises
    EmailAlreadyRegisteredError rather than letting a duplicate-key error
    surface as a raw pymongo exception."""
    if await find_by_email(email) is not None:
        raise EmailAlreadyRegisteredError(email)
    doc = {
        "email": email,
        "hashed_password": hashed_password,
        "created_at": datetime.now(timezone.utc),
    }
    result = await _get_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc_to_user(doc)


async def find_by_email(email: str) -> User | None:
    doc = await _get_collection().find_one({"email": email})
    if doc is None:
        return None
    return _doc_to_user(doc)


async def find_by_id(user_id: str) -> User | None:
    object_id = _to_object_id(user_id)
    if object_id is None:
        return None
    doc = await _get_collection().find_one({"_id": object_id})
    if doc is None:
        return None
    return _doc_to_user(doc)


async def find_or_create_google_user(*, email: str, name: str | None, google_id: str) -> User:
    """
    Resolves a verified Google identity to a StudyGraph user (Phase 9):
    - No account has this email yet -> creates a new password-less account
      (`hashed_password=None`, see app/services/auth_service.py:login, which
      refuses password login for such an account) linked to this Google
      identity.
    - An account with this email exists and is already linked to this exact
      `google_id` -> that's a repeat Google login; returns it as-is (no
      write -- there is nothing to update).
    - An account with this email exists but ISN'T already linked to this
      exact `google_id` -- a password-only account with no google_id yet,
      or one linked to a different google_id -- raises
      GoogleAccountConflictError instead of linking/overwriting. Never
      mutates the document in this case: a matching email is not, by
      itself, proof the caller already owns that account (this is the fix
      for the pre-account-hijacking gap where a Google sign-in could
      silently take over an existing password account).
    `email` must already be normalized -- see
    app/core/google_auth.py:verify_google_id_token.
    """
    existing = await find_by_email(email)
    if existing is None:
        doc = {
            "email": email,
            "hashed_password": None,
            "google_id": google_id,
            "name": name,
            "created_at": datetime.now(timezone.utc),
        }
        result = await _get_collection().insert_one(doc)
        doc["_id"] = result.inserted_id
        return _doc_to_user(doc)

    if existing.google_id != google_id:
        raise GoogleAccountConflictError(email)

    return existing


async def update(user_id: str, *, name: str | None) -> User | None:
    """Applies a profile edit (currently just `name`) and returns the
    updated user, or None if `user_id` doesn't resolve to an existing
    document."""
    object_id = _to_object_id(user_id)
    if object_id is None:
        return None
    doc = await _get_collection().find_one_and_update(
        {"_id": object_id}, {"$set": {"name": name}}, return_document=ReturnDocument.AFTER
    )
    if doc is None:
        return None
    return _doc_to_user(doc)
