"""
Tests for app/services/ingestion/url_extraction.py: the generic (non-YouTube)
URL fetcher/extractor used by app/services/processing_service.py for URL
resources that aren't YouTube links. No real network access is used --
`fetch_url_content` is exercised end-to-end via `httpx.MockTransport`
(intercepts at the transport layer, so no socket is ever opened), and
hostname-based SSRF checks are exercised via monkeypatched
`socket.getaddrinfo`. Test URLs use literal public IP addresses where a
real HTTP round-trip is simulated, so no DNS resolution is needed either.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services.ingestion import url_extraction
from app.services.ingestion.url_extraction import (
    UrlExtractionResult,
    _detect_content_kind,
    _extract_pdf_text,
    _extract_webpage_text,
    fetch_url_content,
    validate_fetchable_url,
)

_PUBLIC_IP_URL = "http://93.184.216.34/page"


def _build_minimal_pdf(text: str = "Hello from a test PDF document.") -> bytes:
    """A hand-built, minimally valid single-page PDF with one text run --
    good enough for pypdf to parse without pulling in a PDF-writing
    dependency just for test fixtures."""
    content = f"BT /F1 24 Tf 72 712 Td ({text}) Tj ET".encode()
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 5 0 R >> >> /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length """ + str(len(content)).encode() + b""" >>
stream
""" + content + b"""
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
trailer
<< /Size 6 /Root 1 0 R >>
startxref
0
%%EOF"""


def _build_pdf_with_no_text() -> bytes:
    """A minimally valid single-page PDF with an empty content stream --
    stands in for a scanned/image-only PDF that has no extractable text."""
    return b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << >> /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 0 >>
stream

endstream
endobj
xref
0 5
0000000000 65535 f
trailer
<< /Size 5 /Root 1 0 R >>
startxref
0
%%EOF"""


@pytest.fixture
def install_mock_transport(monkeypatch):
    """Patches app.services.ingestion.url_extraction's httpx.AsyncClient so
    every request it opens is served by `handler` instead of a real socket.
    """

    def _install(handler):
        transport = httpx.MockTransport(handler)

        class _PatchedAsyncClient(httpx.AsyncClient):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(url_extraction.httpx, "AsyncClient", _PatchedAsyncClient)

    return _install


def _run(coro):
    return asyncio.run(coro)


class TestValidateFetchableUrl:
    def test_unsupported_scheme_is_rejected(self):
        assert validate_fetchable_url("ftp://example.com/file") is not None
        assert validate_fetchable_url("file:///etc/passwd") is not None

    def test_normal_public_ip_literal_is_allowed(self):
        assert validate_fetchable_url(_PUBLIC_IP_URL) is None

    def test_url_with_no_host_is_rejected(self):
        assert validate_fetchable_url("http:///no-host") is not None

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/x",
            "http://127.0.0.1/x",
            "http://127.0.0.1:8000/x",
            "http://10.0.0.5/x",
            "http://192.168.1.1/x",
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
            "http://[::1]/x",
            "http://foo.localhost/x",
        ],
    )
    def test_localhost_and_private_ip_literals_are_rejected(self, url):
        error = validate_fetchable_url(url)
        assert error is not None
        assert "local" in error.lower() or "internal" in error.lower()

    def test_hostname_resolving_to_a_private_address_is_rejected(self, monkeypatch):
        def fake_getaddrinfo(host, port):
            return [(2, 1, 6, "", ("10.1.2.3", 0))]

        monkeypatch.setattr(url_extraction.socket, "getaddrinfo", fake_getaddrinfo)
        error = validate_fetchable_url("http://internal.example.test/x")
        assert error is not None

    def test_hostname_resolving_to_a_public_address_is_allowed(self, monkeypatch):
        def fake_getaddrinfo(host, port):
            return [(2, 1, 6, "", ("93.184.216.34", 0))]

        monkeypatch.setattr(url_extraction.socket, "getaddrinfo", fake_getaddrinfo)
        assert validate_fetchable_url("http://public.example.test/x") is None

    def test_unresolvable_hostname_is_rejected(self, monkeypatch):
        import socket as socket_module

        def fake_getaddrinfo(host, port):
            raise socket_module.gaierror("no such host")

        monkeypatch.setattr(url_extraction.socket, "getaddrinfo", fake_getaddrinfo)
        error = validate_fetchable_url("http://does-not-exist.example.test/x")
        assert error is not None
        assert "resolved" in error.lower()


class TestDetectContentKind:
    def test_html_content_type_detected(self):
        assert _detect_content_kind("text/html; charset=utf-8", "http://x/page") == "html"

    def test_pdf_content_type_detected(self):
        assert _detect_content_kind("application/pdf", "http://x/file") == "pdf"

    def test_pdf_by_url_extension_when_content_type_is_generic(self):
        assert _detect_content_kind("application/octet-stream", "http://x/paper.pdf") == "pdf"
        assert _detect_content_kind(None, "http://x/paper.pdf") == "pdf"

    def test_unsupported_content_type_rejected(self):
        assert _detect_content_kind("image/png", "http://x/pic.png") == "unsupported"
        assert _detect_content_kind("application/json", "http://x/api") == "unsupported"

    def test_missing_content_type_defaults_to_html(self):
        assert _detect_content_kind(None, "http://x/page") == "html"


class TestExtractWebpageText:
    def test_extracts_article_text_and_removes_noise(self):
        html = b"""<html><head><title>Ignored title tag</title>
        <script>trackUser();</script><style>.x{color:red}</style></head>
        <body>
        <nav>Home About Contact Login</nav>
        <article>
          <h1>A Real Heading</h1>
          <p>This is the first real paragraph with genuinely useful article content.</p>
          <p>This is the second paragraph continuing the same article body text.</p>
        </article>
        <footer>Copyright 2024 Example Corp. All rights reserved.</footer>
        </body></html>"""
        text = _extract_webpage_text(html, "http://x/article")
        assert text is not None
        assert "genuinely useful article content" in text
        assert "continuing the same article body" in text
        assert "trackUser" not in text
        assert "color:red" not in text
        assert "Login" not in text
        assert "Copyright 2024" not in text

    def test_empty_page_returns_none(self):
        html = b"<html><head><title>Empty</title></head><body></body></html>"
        assert _extract_webpage_text(html, "http://x/empty") is None

    def test_script_and_style_only_page_returns_none(self):
        html = b"<html><body><script>var x=1;</script><style>.a{color:red}</style></body></html>"
        assert _extract_webpage_text(html, "http://x/empty") is None


class TestExtractPdfText:
    def test_extracts_text_from_valid_pdf(self):
        pdf_bytes = _build_minimal_pdf("This is extractable PDF text content.")
        text = _extract_pdf_text(pdf_bytes)
        assert text is not None
        assert "This is extractable PDF text content." in text

    def test_invalid_pdf_bytes_return_none(self):
        assert _extract_pdf_text(b"this is not a pdf at all") is None

    def test_pdf_with_no_extractable_text_returns_none(self):
        assert _extract_pdf_text(_build_pdf_with_no_text()) is None


class TestFetchUrlContentHtml:
    def test_normal_html_article_extraction_succeeds(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            html = (
                b"<html><body><nav>Home About Contact Login Sign up</nav>"
                b"<article><h1>Title</h1>"
                b"<p>Meaningful article paragraph text goes right here for the test, with "
                b"enough real sentences that the extractor clearly prefers it over boilerplate.</p>"
                b"<p>A second paragraph adds more of the same genuine article body content.</p>"
                b"</article>"
                b"<footer>Copyright 2024 Example Corp. All rights reserved.</footer>"
                b"</body></html>"
            )
            return httpx.Response(200, headers={"content-type": "text/html"}, content=html)

        install_mock_transport(handler)
        result: UrlExtractionResult = _run(fetch_url_content(_PUBLIC_IP_URL))
        assert result.ok
        assert "Meaningful article paragraph text" in result.text
        assert "genuine article body content" in result.text
        assert "Copyright 2024" not in result.text

    def test_empty_webpage_returns_clear_error(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html><body></body></html>")

        install_mock_transport(handler)
        result = _run(fetch_url_content(_PUBLIC_IP_URL))
        assert not result.ok
        assert "no readable" in result.error.lower()

    def test_http_failure_status_returns_clear_error(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, content=b"internal server error")

        install_mock_transport(handler)
        result = _run(fetch_url_content(_PUBLIC_IP_URL))
        assert not result.ok
        assert "fetch" in result.error.lower()

    def test_connection_failure_returns_clear_error(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        install_mock_transport(handler)
        result = _run(fetch_url_content(_PUBLIC_IP_URL))
        assert not result.ok
        assert "fetch" in result.error.lower()

    def test_redirect_is_followed_to_final_content(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == _PUBLIC_IP_URL:
                return httpx.Response(302, headers={"location": "http://93.184.216.34/final"})
            if str(request.url) == "http://93.184.216.34/final":
                html = b"<html><body><article><p>Content reached only after following the redirect.</p></article></body></html>"
                return httpx.Response(200, headers={"content-type": "text/html"}, content=html)
            return httpx.Response(404)

        install_mock_transport(handler)
        result = _run(fetch_url_content(_PUBLIC_IP_URL))
        assert result.ok
        assert "reached only after following the redirect" in result.text

    def test_unsupported_content_type_returns_clear_error(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG\r\n")

        install_mock_transport(handler)
        result = _run(fetch_url_content(_PUBLIC_IP_URL))
        assert not result.ok
        assert "isn't supported" in result.error.lower()


class TestFetchUrlContentPdf:
    def test_direct_pdf_url_extraction_succeeds(self, install_mock_transport):
        pdf_bytes = _build_minimal_pdf("Extracted PDF body text for the test.")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=pdf_bytes)

        install_mock_transport(handler)
        result = _run(fetch_url_content("http://93.184.216.34/paper.pdf"))
        assert result.ok
        assert "Extracted PDF body text for the test." in result.text

    def test_invalid_pdf_returns_clear_error(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"not really a pdf")

        install_mock_transport(handler)
        result = _run(fetch_url_content("http://93.184.216.34/paper.pdf"))
        assert not result.ok
        assert "pdf" in result.error.lower()

    def test_scanned_image_only_pdf_returns_clear_error(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, headers={"content-type": "application/pdf"}, content=_build_pdf_with_no_text()
            )

        install_mock_transport(handler)
        result = _run(fetch_url_content("http://93.184.216.34/scanned.pdf"))
        assert not result.ok
        assert "pdf" in result.error.lower()


class TestFetchUrlContentSsrfGuard:
    def test_localhost_url_is_rejected_without_any_network_call(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for a blocked URL")

        install_mock_transport(handler)
        result = _run(fetch_url_content("http://127.0.0.1:9999/secret"))
        assert not result.ok
        assert "local" in result.error.lower() or "internal" in result.error.lower()

    def test_unsupported_scheme_is_rejected_without_any_network_call(self, install_mock_transport):
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no request should be made for a blocked URL")

        install_mock_transport(handler)
        result = _run(fetch_url_content("file:///etc/passwd"))
        assert not result.ok

    def test_none_source_url_returns_clear_error(self):
        result = _run(fetch_url_content(None))
        assert not result.ok
