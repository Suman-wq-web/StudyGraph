"""
Fetches and extracts readable text from a generic (non-YouTube) URL resource
-- the counterpart to app/services/ingestion/youtube_transcript.py for
`ResourceType.URL` links that aren't YouTube videos. Runs just before the
shared pipeline in app/services/processing_service.py:

    resource -> url_extraction.fetch_url_content(resource.source_url)
             -> content_extraction.extract_content(resource, url_extracted_text=...)
             -> normalize_text() -> chunk_text() -> document_chunks

Handles two content kinds:

  * HTML pages -- readable article/page text is pulled out with
    `trafilatura` (an established readability-style extractor), which drops
    navigation/script/style/menu noise and keeps headings/paragraph text.
  * Direct PDF URLs -- text is extracted per-page with `pypdf`. A
    scanned/image-only PDF (no extractable text layer) surfaces a clear
    error rather than silently producing nothing; OCR is out of scope.

Every other content type (video, images, JSON APIs, ...) is reported as
unsupported rather than guessed at.

Mirrors youtube_transcript.py's result shape and never-raises contract:
`UrlExtractionResult.text` is set on success, `.error` is a short,
user-safe message on failure -- never an internal exception string or
stack trace. `fetch_url_content` never raises; the actual (blocking) HTTP
work runs on an async client so it doesn't need `asyncio.to_thread` the way
the youtube_transcript_api's synchronous library does.

SSRF protection (`validate_fetchable_url`) is deliberately minimal but
real: only http(s) is allowed, and both the literal host and (for a
hostname) every address it resolves to are checked against private/
loopback/link-local/reserved/multicast ranges. Redirects are followed
manually, one hop at a time, so each hop is re-validated the same way --
a malicious server can't redirect a validated public URL into an internal
one. This is not a complete enterprise SSRF system (no DNS-rebinding
protection at the TCP-connect layer), just sensible protection for a
single-tenant study tool. See backend/tests/test_url_extraction.py.
"""

from __future__ import annotations

import io
import ipaddress
import logging
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from pypdf import PdfReader

from app.config import settings

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 StudyGraphBot/1.0"
)
_ACCEPT_HEADER = "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5"
_MAX_REDIRECTS = 5
_BLOCKED_LITERAL_HOSTS = {"localhost", "0.0.0.0"}

_PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
_GENERIC_BINARY_CONTENT_TYPES = {"application/octet-stream", "binary/octet-stream"}

_UNSUPPORTED_SCHEME_MESSAGE = "Only http:// and https:// URLs are supported."
_NO_HOST_MESSAGE = "The URL has no host to fetch."
_BLOCKED_HOST_MESSAGE = (
    "This URL points at a local or internal network address, which is not allowed."
)
_UNRESOLVABLE_HOST_MESSAGE = "The URL's host could not be resolved."
_FETCH_FAILED_MESSAGE = (
    "This URL could not be fetched. It may be down, blocking automated requests, or unreachable."
)
_TOO_LARGE_MESSAGE = "This URL's content is too large to process."
_TOO_MANY_REDIRECTS_MESSAGE = "This URL redirected too many times."
_UNSUPPORTED_CONTENT_TYPE_MESSAGE = (
    "This URL's content type isn't supported for automatic extraction (only HTML pages and "
    "PDF files are). Add the content manually via the content field instead."
)
_NO_READABLE_TEXT_MESSAGE = (
    "No readable article/page text could be extracted from this URL. Add the content manually "
    "via the content field instead."
)
_PDF_NO_TEXT_MESSAGE = (
    "No extractable text was found in this PDF (it may be a scanned/image-only document, which "
    "isn't supported). Add the content manually via the content field instead."
)
_UNEXPECTED_MESSAGE = "An unexpected error occurred while fetching this URL."


@dataclass(frozen=True)
class UrlExtractionResult:
    """`text` is set on success. `error` is a short, user-safe message on
    failure -- never an internal exception string or stack trace."""

    text: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.text is not None


@dataclass(frozen=True)
class _FetchOutcome:
    body: bytes | None = None
    content_type: str | None = None
    final_url: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def validate_fetchable_url(url: str) -> str | None:
    """
    SSRF guard: returns `None` if `url` looks safe to fetch, otherwise a
    short user-safe error message. Rejects non-http(s) schemes, literal
    localhost-ish hosts, and any host (literal IP or resolved hostname)
    that falls in a private/loopback/link-local/reserved/multicast range.
    Pure aside from the DNS lookup, so it's unit-testable with monkeypatched
    `socket.getaddrinfo`.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return _UNSUPPORTED_SCHEME_MESSAGE

    hostname = parsed.hostname
    if not hostname:
        return _NO_HOST_MESSAGE

    lowered = hostname.lower()
    if lowered in _BLOCKED_LITERAL_HOSTS or lowered.endswith(".localhost"):
        return _BLOCKED_HOST_MESSAGE

    try:
        return _blocked_ip_message(ipaddress.ip_address(hostname))
    except ValueError:
        pass  # not a literal IP address -- resolve it as a hostname below

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return _UNRESOLVABLE_HOST_MESSAGE
    for family_info in resolved:
        address = family_info[4][0]
        error = _blocked_ip_message(ipaddress.ip_address(address))
        if error:
            return error
    return None


def _blocked_ip_message(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return _BLOCKED_HOST_MESSAGE
    return None


def _detect_content_kind(content_type: str | None, url: str) -> str:
    """Returns 'pdf', 'html', or 'unsupported'. Prefers the Content-Type
    header; falls back to the URL's file extension when the header is
    missing or a generic binary type, so a server that serves PDFs without
    a correct header (or none at all) is still handled."""
    media_type = (content_type or "").split(";")[0].strip().lower()
    url_path = urlparse(url).path.lower()

    if media_type in _PDF_CONTENT_TYPES:
        return "pdf"
    if media_type in _HTML_CONTENT_TYPES or media_type.startswith("text/"):
        return "html"
    if not media_type or media_type in _GENERIC_BINARY_CONTENT_TYPES:
        if url_path.endswith(".pdf"):
            return "pdf"
        if not media_type:
            return "html"
    return "unsupported"


def _extract_webpage_text(html: bytes, url: str) -> str | None:
    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
    except Exception:
        logger.exception("Unexpected error extracting webpage text for %s", url)
        return None
    if extracted and extracted.strip():
        return extracted.strip()
    return None


def _extract_pdf_text(data: bytes) -> str | None:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return None

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return None

    pages_text: list[str] = []
    for page in reader.pages:
        try:
            page_text = (page.extract_text() or "").strip()
        except Exception:
            page_text = ""
        if page_text:
            pages_text.append(page_text)

    if not pages_text:
        return None
    return "\n\n".join(pages_text)


async def _fetch(url: str) -> _FetchOutcome:
    current_url = url
    timeout = httpx.Timeout(settings.url_fetch_timeout_seconds)
    headers = {"User-Agent": _USER_AGENT, "Accept": _ACCEPT_HEADER}

    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as http_client:
        for _hop in range(_MAX_REDIRECTS + 1):
            validation_error = validate_fetchable_url(current_url)
            if validation_error:
                return _FetchOutcome(error=validation_error)

            try:
                async with http_client.stream("GET", current_url, headers=headers) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return _FetchOutcome(error=_FETCH_FAILED_MESSAGE)
                        current_url = urljoin(str(response.url), location)
                        continue

                    if response.status_code >= 400:
                        return _FetchOutcome(error=_FETCH_FAILED_MESSAGE)

                    body = bytearray()
                    max_bytes = settings.url_fetch_max_bytes
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            return _FetchOutcome(error=_TOO_LARGE_MESSAGE)

                    return _FetchOutcome(
                        body=bytes(body),
                        content_type=response.headers.get("content-type"),
                        final_url=str(response.url),
                    )
            except httpx.RequestError:
                return _FetchOutcome(error=_FETCH_FAILED_MESSAGE)

    return _FetchOutcome(error=_TOO_MANY_REDIRECTS_MESSAGE)


async def fetch_url_content(source_url: str | None) -> UrlExtractionResult:
    """
    Fetches `source_url` and extracts readable text from it (HTML article
    text via trafilatura, or PDF text via pypdf). Never raises -- every
    failure becomes a clear `UrlExtractionResult.error`. Callers are
    responsible for only calling this for non-YouTube URLs (see
    app/services/processing_service.py, which routes YouTube links through
    youtube_transcript.fetch_transcript instead).
    """
    if not source_url:
        return UrlExtractionResult(text=None, error=_NO_HOST_MESSAGE)

    try:
        fetched = await _fetch(source_url)
    except Exception:
        logger.exception("Unexpected error fetching URL %s", source_url)
        return UrlExtractionResult(text=None, error=_UNEXPECTED_MESSAGE)

    if not fetched.ok:
        return UrlExtractionResult(text=None, error=fetched.error)

    assert fetched.body is not None and fetched.final_url is not None
    kind = _detect_content_kind(fetched.content_type, fetched.final_url)

    if kind == "pdf":
        text = _extract_pdf_text(fetched.body)
        if not text:
            return UrlExtractionResult(text=None, error=_PDF_NO_TEXT_MESSAGE)
        return UrlExtractionResult(text=text)

    if kind == "html":
        text = _extract_webpage_text(fetched.body, fetched.final_url)
        if not text:
            return UrlExtractionResult(text=None, error=_NO_READABLE_TEXT_MESSAGE)
        return UrlExtractionResult(text=text)

    return UrlExtractionResult(text=None, error=_UNSUPPORTED_CONTENT_TYPE_MESSAGE)
