from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TaskResponse(ORMModel):
    id: str
    video_id: str
    kind: str
    status: str
    stage: str
    progress: float
    error: str | None
    task_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class Evidence(BaseModel):
    id: str
    source: str
    start_ms: int
    end_ms: int
    content: str
    frame_key: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)

