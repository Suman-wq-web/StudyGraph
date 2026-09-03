"""
Verifies Google Identity Services ID tokens server-side (Phase 9 -- Google
Sign-In). The only module that imports `google.oauth2.id_token` -- mirrors
app/core/security.py being the only module that imports `jose`/`bcrypt`.
"""

from dataclasses import dataclass

from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings

# Shared transport so repeated verifications reuse google-auth's cached
# fetch of Google's public signing keys instead of re-fetching per request.
_google_request = google_requests.Request()


class GoogleAuthError(Exception):
    """Raised for a credential that fails signature/audience/issuer
    verification, or whose email Google hasn't verified --
    app/api/v1/auth.py maps this to a 401, same as InvalidCredentialsError."""


@dataclass(frozen=True)
class GoogleIdentity:
    """The subset of a verified Google ID token's claims this app trusts.
    Never constructed from unverified input -- see verify_google_id_token."""

    subject: str  # Google's stable, per-account `sub` claim.
    email: str
    name: str | None


def verify_google_id_token(credential: str) -> GoogleIdentity:
    """
    Verifies `credential`'s signature (against Google's public keys),
    audience (must match GOOGLE_CLIENT_ID), issuer, and expiry --
    `google.oauth2.id_token.verify_oauth2_token` does all of that. This
    function additionally rejects a token whose `email_verified` claim isn't
    true (verify_oauth2_token doesn't check that itself), since an
    unverified email must never be trusted as a login identifier. Raises
    GoogleAuthError for anything invalid; callers must never read claims out
    of a token that hasn't gone through this function.
    """
    if not settings.google_client_id:
        raise GoogleAuthError("GOOGLE_CLIENT_ID is not configured.")

    try:
        payload = google_id_token.verify_oauth2_token(
            credential, _google_request, settings.google_client_id
        )
    except (ValueError, google_exceptions.GoogleAuthError) as exc:
        raise GoogleAuthError("Invalid Google credential.") from exc

    if not payload.get("email_verified"):
        raise GoogleAuthError("Google account email is not verified.")

    email = payload.get("email")
    subject = payload.get("sub")
    if not email or not subject:
        raise GoogleAuthError("Token is missing required claims.")

    return GoogleIdentity(subject=subject, email=email.strip().lower(), name=payload.get("name"))
