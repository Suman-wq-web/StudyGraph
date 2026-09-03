"""
Embedding provider abstraction (Phase 4).

    EmbeddingProvider (ABC)
        |
        `-- GeminiEmbeddingProvider

The rest of the app depends on `EmbeddingProvider` and `get_embedding_provider()`
-- never on the Gemini SDK directly -- so the backend can switch providers via
the `EMBEDDING_PROVIDER` environment variable alone, with no changes to
app/services/embedding_service.py or anything upstream of it.

Gemini (not OpenAI) is the only implementation for now: the original scaffold
assumed OpenAI, but this project deliberately uses Google's Gemini embedding
API instead to use its free tier and minimize API cost -- see docs/RAG.md.
Uses the current `google-genai` SDK (`google.genai.Client(...).aio.models.
embed_content(...)`), not the deprecated `google-generativeai` package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.config import settings
from app.services.rag.gemini_retry import extract_retry_delay_seconds


class EmbeddingError(Exception):
    """Base for all embedding-provider failures."""


class EmbeddingRateLimitError(EmbeddingError):
    """The provider rejected the request due to a rate limit/quota. Retryable.
    `retry_delay_seconds`, when Gemini's response included one (see
    app/services/rag/gemini_retry.py), is the server-suggested wait before
    retrying -- None if Gemini didn't provide one."""

    def __init__(self, message: str, *, retry_delay_seconds: float | None = None):
        super().__init__(message)
        self.retry_delay_seconds = retry_delay_seconds


class EmbeddingTransientError(EmbeddingError):
    """A transient provider/network failure (5xx, timeout, ...). Retryable."""


class EmbeddingProviderError(EmbeddingError):
    """A non-retryable provider error: bad request, auth failure, misconfiguration,
    or an unexpected/invalid response shape."""


@dataclass(frozen=True)
class EmbeddingVector:
    """One text's embedding. `dimensions` is read off the actual response,
    never assumed, so a config change to the model/output size is reflected
    automatically rather than silently mismatching what's stored."""

    values: list[float]
    dimensions: int


class EmbeddingProvider(ABC):
    """Every embedding backend implements this. Callers (app/services/
    embedding_service.py, app/services/search_service.py) depend on this
    interface, never on a concrete provider class."""

    @abstractmethod
    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        """Embeds chunk text for storage/retrieval (the 'document' side of
        asymmetric retrieval embeddings). Returns vectors in the same order
        as `texts`. Returns `[]` for an empty input rather than calling the
        provider with nothing to embed."""

    @abstractmethod
    async def embed_query(self, text: str) -> EmbeddingVector:
        """Embeds a search query (the 'query' side of asymmetric retrieval
        embeddings) -- Gemini's task-type distinction generally improves
        retrieval quality over embedding both sides identically."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Wraps `google.genai.Client(...).aio.models.embed_content`. Construction
    never makes a network call (the SDK client is lazy), so this is safe to
    instantiate in tests without hitting the real API -- only `embed_documents`/
    `embed_query` do, and those are what tests mock."""

    def __init__(self, *, api_key: str, model: str, output_dimensionality: int | None = None):
        if not api_key:
            raise EmbeddingProviderError(
                "GEMINI_API_KEY is not configured. Set it in backend/.env -- see "
                "docs/ENVIRONMENT.md."
            )
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._output_dimensionality = output_dimensionality

    @property
    def model_name(self) -> str:
        return self._model

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        return await self._embed(texts, task_type="RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> EmbeddingVector:
        vectors = await self._embed([text], task_type="RETRIEVAL_QUERY")
        return vectors[0]

    async def _embed(self, texts: list[str], *, task_type: str) -> list[EmbeddingVector]:
        if not texts:
            return []

        config = genai_types.EmbedContentConfig(task_type=task_type)
        if self._output_dimensionality is not None:
            config.output_dimensionality = self._output_dimensionality

        try:
            response = await self._client.aio.models.embed_content(
                model=self._model, contents=texts, config=config
            )
        except genai_errors.ClientError as exc:
            if exc.code == 429:
                raise EmbeddingRateLimitError(
                    f"Gemini rate limit exceeded: {exc}",
                    retry_delay_seconds=extract_retry_delay_seconds(exc),
                ) from exc
            raise EmbeddingProviderError(f"Gemini rejected the request: {exc}") from exc
        except genai_errors.ServerError as exc:
            raise EmbeddingTransientError(f"Gemini had a transient failure: {exc}") from exc
        except genai_errors.APIError as exc:
            raise EmbeddingProviderError(f"Gemini API error: {exc}") from exc

        embeddings = response.embeddings
        if embeddings is None or len(embeddings) != len(texts):
            raise EmbeddingProviderError(
                "Gemini returned a different number of embeddings than texts submitted."
            )

        vectors: list[EmbeddingVector] = []
        for embedding in embeddings:
            values = embedding.values
            if not values:
                raise EmbeddingProviderError("Gemini returned an empty embedding vector.")
            vectors.append(EmbeddingVector(values=list(values), dimensions=len(values)))
        return vectors


def get_embedding_provider() -> EmbeddingProvider:
    """Provider selection, driven entirely by `settings.embedding_provider`.
    Add a new provider by adding a branch here -- callers never change."""
    provider_name = settings.embedding_provider.strip().lower()
    if provider_name == "gemini":
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_embedding_model,
            output_dimensionality=settings.gemini_embedding_dimensions,
        )
    raise EmbeddingProviderError(
        f"Unknown EMBEDDING_PROVIDER '{settings.embedding_provider}'. Supported: gemini."
    )
