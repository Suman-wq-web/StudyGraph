from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from pydantic.alias_generators import to_camel

from app.models.resource import ResourceType

# A resource counts as "completed" once watched/read past this point, rather
# than requiring exactly 100% -- matches how video/article platforms
# generally treat the last few percent (credits, trailing whitespace) as
# noise rather than meaningfully unfinished content.
COMPLETION_THRESHOLD_PERCENT = 95.0


class ProgressStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ProgressUpdate(BaseModel):
    """
    Request body for PATCH /resources/{id}/progress. Every field is optional
    and only fields explicitly present are applied (service uses
    `exclude_unset`, same convention as ResourceUpdate) -- a video player
    sends `positionSeconds`/`durationSeconds` on each periodic save, a
    reading view sends `progressPercent`, and either may omit `status`
    entirely and let the service derive it.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: ProgressStatus | None = None
    progress_percent: float | None = Field(default=None, ge=0, le=100)
    position_seconds: float | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)


class ResourceProgress(BaseModel):
    """
    Response body: one user's progress on one resource. `id`/`created_at`/
    `updated_at` are `None` for a resource that has no progress activity yet
    -- GET /resources/{id}/progress synthesizes a `not_started` default
    rather than 404ing, since "no progress" is a normal, expected state, not
    an error (see app/services/progress_service.py:get_progress).
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: str | None = None
    user_id: str
    resource_id: str
    status: ProgressStatus = ProgressStatus.NOT_STARTED
    progress_percent: float = 0.0
    position_seconds: float | None = None
    duration_seconds: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class InProgressResource(BaseModel):
    """One row of GET /resources/progress/in-progress -- resource metadata
    flattened together with its progress, so the Dashboard doesn't need a
    second round trip to look up title/type per resource."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    resource_id: str
    title: str
    type: ResourceType
    status: ProgressStatus
    progress_percent: float
    position_seconds: float | None = None
    duration_seconds: float | None = None
    updated_at: datetime


class InProgressResourcesResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[InProgressResource]
