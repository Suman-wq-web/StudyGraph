from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from pydantic.alias_generators import to_camel

MIN_PASSWORD_LENGTH = 8


class UserCredentials(BaseModel):
    """Shared shape for register/login request bodies -- plain email +
    password, matching this codebase's plain-JSON convention (no
    OAuth2PasswordRequestForm form-encoding)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    email: EmailStr
    # max_length=72 matches bcrypt's own input limit (app/core/security.py)
    # -- rejected up front with a clear 422 rather than silently truncated.
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=72)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class User(BaseModel):
    """Schema for the `users` collection. `hashed_password` never leaves
    this module's read path -- see UserPublic for what routes return.
    `hashed_password` is None for an account created via Google Sign-In
    that has never also set a password (see auth_service.login, which
    rejects password login for such an account rather than treating None
    as "any password matches"). `google_id` is the verified Google
    `sub` claim once this account has been linked to a Google identity --
    see app/services/auth_service.py:login_with_google."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    email: str
    hashed_password: str | None = None
    google_id: str | None = None
    name: str | None = None
    created_at: datetime


class UserPublic(BaseModel):
    """Response body for register/`/me`/`PATCH /me` -- never includes hashed_password."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str
    email: str
    name: str | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    """Request body for PATCH /api/v1/auth/me. `name` is the only editable
    profile field -- email is the login identifier and isn't editable here."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        return v or None


class GoogleAuthRequest(BaseModel):
    """Request body for POST /api/v1/auth/google. `credential` is the raw
    ID token (a signed JWT) handed to the frontend by Google Identity
    Services -- never trusted as-is, see
    app/services/auth_service.py:login_with_google, which verifies its
    signature/audience/issuer server-side before reading any claim out of
    it."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    credential: str = Field(..., min_length=1)


class Token(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    access_token: str
    token_type: str = "bearer"


class MigrationResult(BaseModel):
    """Response body for POST /api/v1/auth/claim-legacy-data -- counts of
    pre-auth (`single-tenant-user`-owned or user_id-less) documents
    reassigned to the caller. All zero on a second call -- idempotent, see
    app/services/migration_service.py."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    resources_migrated: int
    document_chunks_migrated: int
    concepts_migrated: int
    edges_migrated: int
