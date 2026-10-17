from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class VideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source_type: str
    source_url: str | None
    mime_type: str | None
    size_bytes: int | None
    duration_ms: int | None
    status: str
    error: str | None
    media_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class VideoListResponse(BaseModel):
    items: list[VideoResponse]
    total: int


class PlaybackResponse(BaseModel):
    url: str
    expires_in: int


class SegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    start_ms: int
    end_ms: int
    transcript: str
    visual_text: str
    frame_keys: list[str]

