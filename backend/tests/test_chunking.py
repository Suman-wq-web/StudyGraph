import pytest
import tiktoken

from app.services.ingestion.chunking import chunk_text

ENCODING = tiktoken.get_encoding("cl100k_base")


def _tokens_text(n: int, word: str = "token") -> str:
    """Builds a string that encodes to exactly `n` tokens under cl100k_base.
    Self-validating: fails loudly if tiktoken's tokenization of the fixture
    ever drifts, rather than silently testing the wrong token count."""
    if n == 0:
        return ""
    text = ((" " + word) * n).strip()
    actual = len(ENCODING.encode(text))
    assert actual == n, f"fixture drift: expected {n} tokens, got {actual}"
    return text


class TestEmptyAndTrivialContent:
    def test_empty_string_returns_no_chunks(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_no_chunks(self):
        assert chunk_text("   \n\t  \n  ") == []

    def test_very_short_content_returns_one_chunk(self):
        chunks = chunk_text("Hello world.")
        assert len(chunks) == 1
        assert chunks[0].start_token == 0
        assert chunks[0].token_count == len(ENCODING.encode("Hello world."))
        assert chunks[0].end_token == chunks[0].token_count


class TestSizeBoundaries:
    def test_content_under_max_tokens_is_a_single_chunk(self):
        text = _tokens_text(300)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        assert len(chunks) == 1
        assert chunks[0].token_count == 300
        assert chunks[0].start_token == 0
        assert chunks[0].end_token == 300

    def test_content_exactly_at_max_tokens_is_a_single_chunk(self):
        text = _tokens_text(512)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        assert len(chunks) == 1
        assert chunks[0].token_count == 512
        assert chunks[0].start_token == 0
        assert chunks[0].end_token == 512

    def test_content_one_token_over_max_produces_second_chunk(self):
        text = _tokens_text(513)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        assert len(chunks) == 2
        assert chunks[0].start_token == 0
        assert chunks[0].end_token == 512
        # step = max_tokens - overlap_tokens = 448
        assert chunks[1].start_token == 448
        assert chunks[1].end_token == 513
        assert chunks[1].token_count == 65

    def test_large_document_covers_every_token_without_truncation(self):
        text = _tokens_text(2000)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        assert len(chunks) > 1
        assert chunks[0].start_token == 0
        assert chunks[-1].end_token == 2000  # never silently truncated


class TestOverlapAndOrdering:
    def test_overlap_between_consecutive_chunks_matches_config(self):
        text = _tokens_text(2000)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        for prev, nxt in zip(chunks, chunks[1:-1]):  # exclude a possibly-short final chunk
            assert prev.end_token - nxt.start_token == 64

    def test_chunks_are_returned_in_source_order(self):
        text = _tokens_text(2000)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        starts = [c.start_token for c in chunks]
        assert starts == sorted(starts)
        assert starts == sorted(set(starts))  # strictly increasing, no repeats

    def test_small_custom_window_for_easy_manual_verification(self):
        text = _tokens_text(25)
        chunks = chunk_text(text, max_tokens=10, overlap_tokens=3)
        # step = 7: starts at 0, 7, 14, 21
        assert [c.start_token for c in chunks] == [0, 7, 14, 21]
        assert [c.end_token for c in chunks] == [10, 17, 24, 25]
        assert [c.token_count for c in chunks] == [10, 10, 10, 4]


class TestTokenCountsAndEmptyChunks:
    def test_token_count_matches_end_minus_start_for_every_chunk(self):
        text = _tokens_text(1500)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        for c in chunks:
            assert c.token_count == c.end_token - c.start_token

    def test_token_count_matches_reencoding_the_chunk_text(self):
        text = _tokens_text(1500)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        for c in chunks:
            assert len(ENCODING.encode(c.text)) == c.token_count

    def test_no_chunk_is_ever_empty(self):
        text = _tokens_text(2000)
        chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        assert all(c.text.strip() for c in chunks)

    def test_pathological_whitespace_heavy_text_produces_no_empty_chunks(self):
        text = "word " + ("\n" * 5000) + " word"
        chunks = chunk_text(text, max_tokens=50, overlap_tokens=10)
        assert all(c.text.strip() for c in chunks)


class TestDeterminism:
    def test_same_input_and_config_produces_identical_output(self):
        text = _tokens_text(1200)
        first = chunk_text(text, max_tokens=512, overlap_tokens=64)
        second = chunk_text(text, max_tokens=512, overlap_tokens=64)
        assert first == second

    def test_uses_configured_defaults_when_not_overridden(self):
        text = _tokens_text(1200)
        default_chunks = chunk_text(text)
        explicit_chunks = chunk_text(text, max_tokens=512, overlap_tokens=64)
        assert default_chunks == explicit_chunks


class TestValidation:
    def test_rejects_non_positive_max_tokens(self):
        with pytest.raises(ValueError):
            chunk_text("hello", max_tokens=0, overlap_tokens=0)

    def test_rejects_negative_overlap(self):
        with pytest.raises(ValueError):
            chunk_text("hello", max_tokens=10, overlap_tokens=-1)

    def test_rejects_overlap_greater_than_or_equal_to_max_tokens(self):
        with pytest.raises(ValueError):
            chunk_text("hello", max_tokens=10, overlap_tokens=10)
