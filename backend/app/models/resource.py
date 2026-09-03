from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

MAX_TAGS = 20
MAX_TAG_LENGTH = 50


class ResourceType(str, Enum):
    ARTICLE = "article"
    URL = "url"
    VIDEO = "video"
    NOTE = "note"


class ResourceStatus(str, Enum):
    """
    Processing lifecycle for a resource, spanning both the chunking (Phase 3)
    and embedding (Phase 4) pipelines:

        PENDING -> PROCESSING -> READY -> EMBEDDING -> EMBEDDED
                        \\-> FAILED <-/         \\-> FAILED

    PENDING is the state every resource is created in.
    POST /resources/{id}/process (app/services/processing_service.py) moves
    it PROCESSING -> READY (chunks written to `document_chunks`) or FAILED.
    POST /resources/{id}/embed (app/services/embedding_service.py) then
    moves a READY (or previously EMBEDDED/FAILED-while-embedding) resource
    EMBEDDING -> EMBEDDED (every chunk has a vector) or FAILED. Re-chunking a
    resource (re-running /process) replaces its chunks and their embeddings
    outright, so status drops back to READY -- it must be re-embedded.
    `Resource.processing_error` carries the reason for the most recent
    FAILED, from whichever stage caused it.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    EMBEDDING = "embedding"
    EMBEDDED = "embedded"
    FAILED = "failed"


def _clean_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = raw.strip().lower()
        if not tag:
            continue
        if len(tag) > MAX_TAG_LENGTH:
            raise ValueError(f"Tag '{raw}' exceeds {MAX_TAG_LENGTH} characters")
        if tag not in seen:
            seen.add(tag)
            cleaned.append(tag)
    if len(cleaned) > MAX_TAGS:
        raise ValueError(f"A resource may have at most {MAX_TAGS} tags")
    return cleaned


def _clean_source_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("source_url must start with http:// or https://")
    return value


class ResourceBase(BaseModel):
    """
    Shared fields/validation for create and update payloads. The wire format
    is camelCase (sourceUrl, createdAt, ...) via alias_generator, matching
    frontend TypeScript conventions; `populate_by_name` lets input use
    either the alias or the underlying snake_case field name.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    type: ResourceType
    source_url: str | None = Field(default=None, max_length=2048)
    content: str | None = Field(default=None, max_length=200_000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        return v

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, v: str | None) -> str | None:
        return _clean_source_url(v)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str]) -> list[str]:
        return _clean_tags(v)


class ResourceCreate(ResourceBase):
    """Request body for POST /api/v1/resources. Status always starts at PENDING."""


class ResourceUpdate(BaseModel):
    """
    Request body for PATCH /api/v1/resources/{id}. Every field is optional --
    only fields explicitly present in the request are applied (see
    resource_service.update_resource, which uses `exclude_unset`).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    type: ResourceType | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    content: str | None = Field(default=None, max_length=200_000)
    tags: list[str] | None = None
    status: ResourceStatus | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("title cannot be empty")
        return v

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, v: str | None) -> str | None:
        return _clean_source_url(v)

    @field_validator("tags")
    @classmethod
    def _validate_tags(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _clean_tags(v)


class Resource(ResourceBase):
    """
    Response body: a resource as stored, with server-assigned fields.
    `processing_error` is server-managed (set by the processing pipeline, not
    user input) so it deliberately isn't on ResourceCreate/ResourceUpdate --
    see app/db/resource_repository.py:set_processing_state. `user_id`
    (Phase 8) is likewise server-assigned from the caller's auth token, not
    client-supplied -- required, no default, same as Concept.user_id/
    ConceptEdge.user_id (app/models/concept.py, edge.py). A resource written
    before Phase 8 has no `user_id` at all until claimed via
    POST /api/v1/auth/claim-legacy-data (app/services/migration_service.py);
    every read query is itself user_id-scoped, so such a row is simply never
    fetched (and never reaches this model) until then -- see
    docs/DATABASE.md ("Migrating pre-auth data").
    """

    id: str
    user_id: str
    status: ResourceStatus = ResourceStatus.PENDING
    processing_error: str | None = Field(default=None, max_length=2000)
    created_at: datetime
    updated_at: datetime


class ResourceListResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[Resource]
    total: int
    skip: int
    limit: int


class ResourceStats(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    total: int
    by_type: dict[str, int]
    by_status: dict[str, int]
