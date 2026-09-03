"""
Generation provider abstraction (Phase 5). Mirrors app/services/rag/
embeddings.py exactly:

    GenerationProvider (ABC)
        |
        `-- GeminiGenerationProvider

app/services/rag/pipeline.py depends on `GenerationProvider` and
`get_generation_provider()` -- never on the Gemini SDK directly -- so
generation can switch providers via the `GENERATION_PROVIDER` environment
variable alone, with no changes upstream.

Gemini generation reuses the same `GEMINI_API_KEY` and the same
`google.genai` SDK client class as embeddings, just calling
`generate_content_stream(...)` instead of `embed_content(...)` --
`embeddings.py` and this module are the only two modules that import
`google.genai`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.config import settings
from app.services.rag.gemini_retry import extract_retry_delay_seconds


class GenerationError(Exception):
    """Base for all generation-provider failures."""


class GenerationRateLimitError(GenerationError):
    """The provider rejected the request due to a rate limit/quota. Retryable.
    `retry_delay_seconds`, when Gemini's response included one (see
    app/services/rag/gemini_retry.py), is the server-suggested wait before
    retrying -- None if Gemini didn't provide one."""

    def __init__(self, message: str, *, retry_delay_seconds: float | None = None):
        super().__init__(message)
        self.retry_delay_seconds = retry_delay_seconds


class GenerationTransientError(GenerationError):
    """A transient provider/network failure (5xx, timeout, ...). Retryable."""


class GenerationProviderError(GenerationError):
    """A non-retryable provider error: bad request, auth failure, misconfiguration,
    or an unexpected/invalid response shape."""


@dataclass(frozen=True)
class GenerationChunk:
    """One streamed delta. `finish_reason` is set only on the terminal chunk
    of a successful stream (e.g. "STOP"), None otherwise."""

    text: str
    finish_reason: str | None = None


class GenerationProvider(ABC):
    """Every generation backend implements this. app/services/rag/pipeline.py
    depends on this interface, never on a concrete provider class."""

    @abstractmethod
    def stream_generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[GenerationChunk]:
        """Streams the model's response to `user_prompt`, grounded by
        `system_prompt`, as a sequence of text deltas."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...


class GeminiGenerationProvider(GenerationProvider):
    """Wraps `google.genai.Client(...).aio.models.generate_content_stream`.
    Construction never makes a network call (the SDK client is lazy), so
    this is safe to instantiate in tests without hitting the real API --
    only `stream_generate` does, and that's what tests mock."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ):
        if not api_key:
            raise GenerationProviderError(
                "GEMINI_API_KEY is not configured. Set it in backend/.env -- see "
                "docs/ENVIRONMENT.md."
            )
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

    @property
    def model_name(self) -> str:
        return self._model

    async def stream_generate(
        self, *, system_prompt: str, user_prompt: str
    ) -> AsyncIterator[GenerationChunk]:
        config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self._temperature,
            max_output_tokens=self._max_output_tokens,
        )

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model, contents=user_prompt, config=config
            )
            async for response in stream:
                finish_reason = None
                if response.candidates:
                    reason = response.candidates[0].finish_reason
                    if reason is not None:
                        finish_reason = reason.value
                yield GenerationChunk(text=response.text or "", finish_reason=finish_reason)
        except genai_errors.ClientError as exc:
            if exc.code == 429:
                raise GenerationRateLimitError(
                    f"Gemini rate limit exceeded: {exc}",
                    retry_delay_seconds=extract_retry_delay_seconds(exc),
                ) from exc
            raise GenerationProviderError(f"Gemini rejected the request: {exc}") from exc
        except genai_errors.ServerError as exc:
            raise GenerationTransientError(f"Gemini had a transient failure: {exc}") from exc
        except genai_errors.APIError as exc:
            raise GenerationProviderError(f"Gemini API error: {exc}") from exc


def get_generation_provider() -> GenerationProvider:
    """Provider selection, driven entirely by `settings.generation_provider`.
    Add a new provider by adding a branch here -- callers never change."""
    provider_name = settings.generation_provider.strip().lower()
    if provider_name == "gemini":
        return GeminiGenerationProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_chat_model,
            temperature=settings.gemini_chat_temperature,
            max_output_tokens=settings.gemini_chat_max_output_tokens,
        )
    raise GenerationProviderError(
        f"Unknown GENERATION_PROVIDER '{settings.generation_provider}'. Supported: gemini."
    )
