from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized environment configuration. See .env.example for the full list."""

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "studygraph"
    allowed_origins: str = "http://localhost:3000"

    # Document-processing pipeline (Phase 3). Centralized here so chunk size
    # and overlap are configured in one place rather than hard-coded across
    # the codebase -- see app/services/ingestion/chunking.py.
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64
    tiktoken_encoding: str = "cl100k_base"

    # Embeddings (Phase 4). `embedding_provider` selects the implementation
    # returned by app/services/rag/embeddings.py:get_embedding_provider() --
    # the rest of the app depends on that abstraction, never on a concrete
    # SDK, so swapping providers later is a config change, not a rewrite.
    # Gemini is used instead of OpenAI (the original scaffold's plan) to use
    # Google's free tier and minimize cost -- see docs/RAG.md.
    embedding_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_embedding_model: str = "gemini-embedding-001"
    # None = the model's own default (3072 for gemini-embedding-001). Set to
    # 768/1536/3072 to use Matryoshka Representation Learning truncation --
    # whatever this resolves to becomes the *actual* stored vector length;
    # nothing in this codebase hard-codes a dimension count.
    gemini_embedding_dimensions: int | None = None
    # Chunks per embed_content() call -- batches large resources into
    # several requests rather than one unbounded call.
    embedding_batch_size: int = 32
    # Auto-chain processing -> embedding: when true (the default),
    # processing_service.run_processing() kicks off embedding_service's own
    # start/run pipeline immediately after a resource reaches READY, so a
    # newly added resource becomes semantically searchable without a
    # separate manual "Embed" click. The manual endpoint/button stays as a
    # retry/recovery path regardless (e.g. after a FAILED auto-embed, or if
    # this is turned off). tests/conftest.py overrides this to false for the
    # test suite, so tests that only care about the chunking stage don't
    # also make embedding-provider calls just because they process a
    # resource.
    auto_embed_after_processing: bool = True

    # Generation (Phase 5). `generation_provider` selects the implementation
    # returned by app/services/rag/generation.py:get_generation_provider() --
    # mirrors embedding_provider's dispatch pattern. Gemini generation reuses
    # the same GEMINI_API_KEY as embeddings and the same google.genai SDK
    # client, just calling generate_content_stream instead of embed_content.
    generation_provider: str = "gemini"
    gemini_chat_model: str = "gemini-3.6-flash"
    gemini_chat_temperature: float = 0.2
    gemini_chat_max_output_tokens: int | None = 1024

    # Hybrid retrieval (Phase 5). See app/services/rag/retrieval.py.
    rag_default_top_k: int = 8
    # Each retriever (vector, BM25) is queried for max(top_k * this,
    # rag_min_candidate_pool) candidates before reciprocal rank fusion, so
    # fusion has more signal to work with than the caller's final top_k.
    rag_candidate_multiplier: int = 4
    rag_min_candidate_pool: int = 20
    # Reciprocal rank fusion constant -- the standard literature default.
    rag_rrf_k: int = 60
    # Citation snippet truncation length (the full chunk text still goes
    # into the LLM prompt; only the client-facing citation is trimmed).
    rag_max_snippet_chars: int = 320

    # Knowledge graph extraction (Phase 6). Reuses the existing
    # GenerationProvider as-is (GEMINI_API_KEY, GEMINI_CHAT_MODEL) -- no
    # separate provider/model/key, since app/services/rag/generation.py is
    # deliberately left untouched; see app/services/ingestion/extraction.py.
    extraction_max_concepts_per_chunk: int = 8

    # Generic URL content extraction (Phase 3). Used by
    # app/services/ingestion/url_extraction.py for URL resources whose
    # source_url isn't a YouTube link (those go through
    # youtube_transcript.py instead, unaffected by these settings).
    url_fetch_timeout_seconds: float = 15.0
    url_fetch_max_bytes: int = 10_000_000  # 10 MB

    # Auth (Phase 8). Empty by default (fails clearly at token
    # creation/verification, app/core/security.py:TokenError) rather than
    # silently signing with a blank secret -- every real deployment must set
    # a real JWT_SECRET_KEY, never committed. See docs/ENVIRONMENT.md.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 10080  # 7 days

    # Google Sign-In (ID-token flow -- see app/services/auth_service.py:
    # login_with_google). Only the client ID is needed: the backend verifies
    # a Google-issued ID token's signature against Google's public keys, it
    # never calls Google with a client secret. Must match the frontend's
    # NEXT_PUBLIC_GOOGLE_CLIENT_ID -- both are the same OAuth client's public
    # ID, not a secret. Empty by default (fails clearly, GoogleAuthError,
    # rather than silently accepting tokens for the wrong audience).
    google_client_id: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


settings = Settings()
