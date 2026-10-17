from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    id: str = Field(description="Short stable identifier such as step_1")
    objective: str
    search_query: str


class AnalysisPlan(BaseModel):
    title: str
    steps: list[PlanStep] = Field(min_length=1, max_length=5)


class Finding(BaseModel):
    step_id: str
    conclusion: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)


class Critique(BaseModel):
    approved: bool
    feedback: str
    missing_aspects: list[str] = Field(default_factory=list)


class Chapter(BaseModel):
    start_ms: int
    end_ms: int
    title: str
    summary: str


class ReportConclusion(BaseModel):
    text: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)


class VideoReport(BaseModel):
    title: str
    executive_summary: str
    chapters: list[Chapter]
    conclusions: list[ReportConclusion]
    action_items: list[str]
    suggestions: list[str]


class RetrievedEvidence(BaseModel):
    id: str
    source: Literal["ASR", "VISION"]
    start_ms: int
    end_ms: int
    content: str
    frame_key: str | None = None
    score: float = 0.0

