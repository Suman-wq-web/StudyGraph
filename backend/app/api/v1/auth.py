"""Registration/login/`/me` and the one-time legacy-data claim (Phase 8).
See docs/API.md ("Auth") and docs/DATABASE.md ("Migrating pre-auth data")."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user_id
from app.db.user_repository import EmailAlreadyRegisteredError
from app.models.user import (
    GoogleAuthRequest,
    MigrationResult,
    Token,
    UserCredentials,
    UserPublic,
    UserUpdate,
)
from app.services import auth_service, migration_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCredentials) -> UserPublic:
    try:
        return await auth_service.register(payload)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered."
        ) from exc


@router.post("/login", response_model=Token)
async def login(payload: UserCredentials) -> Token:
    try:
        return await auth_service.login(payload)
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        ) from exc


@router.post("/google", response_model=Token)
async def login_with_google(payload: GoogleAuthRequest) -> Token:
    """
    Verifies `payload.credential` (a Google Identity Services ID token)
    server-side and issues the same kind of access token `/login` does --
    see app/services/auth_service.py:login_with_google and
    app/core/google_auth.py. An existing email/password account with a
    matching email is linked and logged into rather than duplicated; a new
    email is registered as a password-less account.
    """
    try:
        return await auth_service.login_with_google(payload.credential)
    except auth_service.GoogleAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc


@router.get("/me", response_model=UserPublic)
async def get_me(current_user_id: str = Depends(get_current_user_id)) -> UserPublic:
    user = await auth_service.get_current_user(current_user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/me", response_model=UserPublic)
async def update_me(
    payload: UserUpdate, current_user_id: str = Depends(get_current_user_id)
) -> UserPublic:
    user = await auth_service.update_profile(current_user_id, payload)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/claim-legacy-data", response_model=MigrationResult)
async def claim_legacy_data(current_user_id: str = Depends(get_current_user_id)) -> MigrationResult:
    """
    Reassigns every pre-auth `resources`/`document_chunks`/`concepts`/
    `edges` document (the old single-tenant placeholder owner, or --
    for resources/document_chunks, which predate the `user_id` field
    entirely -- no owner at all) to the calling user. Always targets the
    caller's own id; never deletes anything; safe to call more than once
    (a second call finds nothing left to claim). See
    app/services/migration_service.py.
    """
    counts = await migration_service.migrate_legacy_data(current_user_id)
    return MigrationResult(
        resources_migrated=counts.resources_migrated,
        document_chunks_migrated=counts.document_chunks_migrated,
        concepts_migrated=counts.concepts_migrated,
        edges_migrated=counts.edges_migrated,
    )
