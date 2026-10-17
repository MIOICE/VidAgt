from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.time import utc_now
from app.models.enums import AnalysisStatus, TaskStatus, UploadStatus, VideoStatus


def uuid4_str() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )


class Video(TimestampMixin, Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(String(512))
    preview_key: Mapped[str | None] = mapped_column(String(512))
    sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(24), default=VideoStatus.QUEUED, index=True)
    error: Mapped[str | None] = mapped_column(Text)
    media_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    tasks: Mapped[list[ProcessingTask]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    segments: Mapped[list[VideoSegment]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    semantic_chunks: Mapped[list[SemanticChunk]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    keyframes: Mapped[list[Keyframe]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    analyses: Mapped[list[AnalysisRun]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class UploadSession(TimestampMixin, Base):
    __tablename__ = "upload_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    multipart_id: Mapped[str] = mapped_column(String(255), nullable=False)
    part_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=UploadStatus.CREATED, index=True)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"))


class ProcessingTask(TimestampMixin, Base):
    __tablename__ = "processing_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), default="PROCESS")
    status: Mapped[str] = mapped_column(String(24), default=TaskStatus.PENDING, index=True)
    stage: Mapped[str] = mapped_column(String(32), default="QUEUED")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    celery_task_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    task_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    video: Mapped[Video] = relationship(back_populates="tasks")


class VideoSegment(Base):
    __tablename__ = "video_segments"
    __table_args__ = (
        Index("ix_video_segments_video_start", "video_id", "start_ms"),
        UniqueConstraint("video_id", "start_ms", "end_ms", name="uq_video_segment_window"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, default="")
    visual_text: Mapped[str] = mapped_column(Text, default="")
    frame_keys: Mapped[list[str]] = mapped_column(JSON, default=list)

    video: Mapped[Video] = relationship(back_populates="segments")


class SemanticChunk(Base):
    __tablename__ = "semantic_chunks"
    __table_args__ = (Index("ix_semantic_chunks_video_start", "video_id", "start_ms"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list)

    video: Mapped[Video] = relationship(back_populates="semantic_chunks")


class Keyframe(Base):
    __tablename__ = "keyframes"
    __table_args__ = (Index("ix_keyframes_video_timestamp", "video_id", "timestamp_ms"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    scene_score: Mapped[float] = mapped_column(Float, default=0.0)

    video: Mapped[Video] = relationship(back_populates="keyframes")


class AnalysisRun(TimestampMixin, Base):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(24), default="AUTO_REPORT")
    language: Mapped[str] = mapped_column(String(16), default="auto")
    status: Mapped[str] = mapped_column(String(24), default=AnalysisStatus.PENDING, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    graph_thread_id: Mapped[str] = mapped_column(String(64), default=uuid4_str)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    video: Mapped[Video] = relationship(back_populates="analyses")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    video_id: Mapped[str] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="视频问答")
    graph_thread_id: Mapped[str] = mapped_column(String(64), default=uuid4_str)

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
