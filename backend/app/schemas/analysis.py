from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Evidence


class AnalysisCreate(BaseModel):
    goal: str = Field(
        default="生成结构化视频报告，包含摘要、章节、关键结论和行动建议。",
        min_length=4,
        max_length=4000,
    )
    mode: Literal["AUTO_REPORT", "CUSTOM"] = "AUTO_REPORT"
    language: Literal["auto", "zh", "en"] = "auto"


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    video_id: str
    goal: str
    mode: str
    language: str
    status: str
    progress: float
    plan: dict[str, Any]
    report: dict[str, Any]
    error: str | None
    created_at: datetime
    updated_at: datetime


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    answer: str
    evidence: list[Evidence]


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: Literal["user", "assistant"]
    content: str
    evidence: list[Evidence]
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    conversation_id: str | None
    messages: list[ChatHistoryMessage]
