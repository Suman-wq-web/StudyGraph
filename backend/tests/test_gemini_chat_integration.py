"""
Opt-in integration test that makes a REAL call to the Gemini generation API.
Skipped by default -- every other test in this suite mocks the provider (see
test_generation.py); this one exists to verify the actual SDK usage against
the real service when a developer explicitly wants that.

Reuses the same RUN_GEMINI_INTEGRATION_TESTS/GEMINI_API_KEY flags as
test_gemini_integration.py (the embedding equivalent) -- both exercise the
same Gemini account, just two different API surfaces (embed vs. generate).

Enable with:
    RUN_GEMINI_INTEGRATION_TESTS=1 GEMINI_API_KEY=<real key> \\
    pytest tests/test_gemini_chat_integration.py
"""

import asyncio
import os

import pytest

from app.services.rag.generation import GeminiGenerationProvider

_RUN = os.environ.get("RUN_GEMINI_INTEGRATION_TESTS") == "1"
_API_KEY = os.environ.get("GEMINI_API_KEY", "")

pytestmark = pytest.mark.skipif(
    not _RUN or not _API_KEY,
    reason="Set RUN_GEMINI_INTEGRATION_TESTS=1 and a real GEMINI_API_KEY to run this test.",
)


def test_real_gemini_generation_call_returns_a_nonempty_streamed_answer():
    provider = GeminiGenerationProvider(api_key=_API_KEY, model="gemini-2.5-flash")

    async def scenario() -> str:
        parts: list[str] = []
        async for chunk in provider.stream_generate(
            system_prompt="You are a terse assistant. Answer in one short sentence.",
            user_prompt="What is 2 + 2?",
        ):
            parts.append(chunk.text)
        return "".join(parts)

    answer = asyncio.run(scenario())

    assert answer.strip()
    assert "4" in answer
