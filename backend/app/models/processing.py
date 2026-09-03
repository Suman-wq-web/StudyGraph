from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.models.resource import ResourceStatus


class ProcessingStatusResponse(BaseModel):
    """Response body for GET /resources/{id}/processing-status."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    resource_id: str
    status: ResourceStatus
    chunk_count: int
    processing_error: str | None = None
    updated_at: datetime
