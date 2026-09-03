"""Tests for app/services/rag/gemini_retry.py's retryDelay extraction."""

import pytest
from google.genai import errors as genai_errors

from app.services.rag.gemini_retry import extract_retry_delay_seconds


def _client_error(details_list: list | None) -> genai_errors.ClientError:
    error: dict = {"message": "quota exceeded", "status": "RESOURCE_EXHAUSTED"}
    if details_list is not None:
        error["details"] = details_list
    return genai_errors.ClientError(429, {"error": error})


class TestExtractRetryDelaySeconds:
    def test_returns_seconds_from_retry_info_detail(self):
        exc = _client_error(
            [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "19s"}]
        )
        assert extract_retry_delay_seconds(exc) == 19.0

    def test_parses_fractional_seconds(self):
        exc = _client_error(
            [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "1.500s"}]
        )
        assert extract_retry_delay_seconds(exc) == pytest.approx(1.5)

    def test_returns_none_when_no_details_present(self):
        exc = _client_error(None)
        assert extract_retry_delay_seconds(exc) is None

    def test_returns_none_when_details_has_no_retry_info(self):
        exc = _client_error([{"@type": "type.googleapis.com/google.rpc.Help", "links": []}])
        assert extract_retry_delay_seconds(exc) is None

    def test_returns_none_for_malformed_retry_delay(self):
        exc = _client_error(
            [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "soon"}]
        )
        assert extract_retry_delay_seconds(exc) is None

    def test_skips_non_dict_detail_entries(self):
        exc = _client_error(["not-a-dict"])
        assert extract_retry_delay_seconds(exc) is None

    def test_finds_retry_info_among_multiple_details(self):
        exc = _client_error(
            [
                {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": []},
                {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "5s"},
            ]
        )
        assert extract_retry_delay_seconds(exc) == 5.0

    def test_returns_none_for_a_non_429_error_without_details(self):
        error = genai_errors.ClientError(
            400, {"error": {"message": "bad request", "status": "INVALID_ARGUMENT"}}
        )
        assert extract_retry_delay_seconds(error) is None
