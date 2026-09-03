"""
Shared helper for the two Gemini provider wrappers (app/services/rag/
embeddings.py, app/services/rag/generation.py): extracts the server-
suggested retry delay from a Gemini 429 response, when present, so the
retry loops that call them (app/services/embedding_service.py,
app/services/rag/pipeline.py) can wait as long as Gemini actually asked
instead of guessing with a fixed backoff schedule.

Gemini reports this via a `google.rpc.RetryInfo` protobuf detail in the
error body, e.g.:

    {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo",
         "retryDelay": "19s"}
    ]}}

`google-genai`'s `APIError.details` is already the parsed JSON error body
(see the installed `google/genai/errors.py`), so no extra parsing
dependency is needed here -- just reading the shape above.
"""

from __future__ import annotations

from google.genai import errors as genai_errors


def extract_retry_delay_seconds(exc: genai_errors.APIError) -> float | None:
    """Returns the `retryDelay` Gemini suggested in `exc`'s error body, in
    seconds, or None if the response didn't include one or it couldn't be
    parsed -- callers fall back to their own default backoff in that case.
    Never raises: a missing/malformed error body just yields None."""
    error_body = _error_body(exc)
    if error_body is None:
        return None
    for detail in error_body.get("details") or []:
        if not isinstance(detail, dict):
            continue
        seconds = _parse_duration_string(detail.get("retryDelay"))
        if seconds is not None:
            return seconds
    return None


def _error_body(exc: genai_errors.APIError) -> dict | None:
    details = getattr(exc, "details", None)
    if not isinstance(details, dict):
        return None
    # `details` is either the raw `{"error": {...}}` response body or
    # already just the inner error dict, depending on which SDK code path
    # constructed it -- handle both without guessing which one applies.
    error_body = details.get("error", details)
    return error_body if isinstance(error_body, dict) else None


def _parse_duration_string(value: object) -> float | None:
    """Parses a protobuf `Duration` string like "19s" or "1.500s"."""
    if not isinstance(value, str) or not value.endswith("s"):
        return None
    try:
        seconds = float(value[:-1])
    except ValueError:
        return None
    return seconds if seconds >= 0 else None
