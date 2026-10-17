from __future__ import annotations

import math
import re

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import RetrievedEvidence
from app.models.entities import SemanticChunk, VideoSegment
from app.services.ai_provider import ai_provider


def _tokens(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z0-9_]{2,}", lowered))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    words.update(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    return {token for token in words if token}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(value * value for value in left))
    norm_right = math.sqrt(sum(value * value for value in right))
    if not norm_left or not norm_right:
        return 0.0
    return dot / (norm_left * norm_right)


async def hybrid_retrieve(
    db: AsyncSession, video_id: str, query: str, top_k: int = 6
) -> list[RetrievedEvidence]:
    chunks = list(
        (
            await db.scalars(
                select(SemanticChunk)
                .where(SemanticChunk.video_id == video_id)
                .order_by(SemanticChunk.start_ms)
            )
        ).all()
    )
    query_embedding: list[float] = []
    if ai_provider.configured and any(chunk.embedding for chunk in chunks):
        query_embedding = await ai_provider.embed_query(query)
    query_tokens = _tokens(query)
    scored: list[tuple[float, SemanticChunk]] = []
    for chunk in chunks:
        chunk_tokens = _tokens(f"{chunk.summary} {' '.join(chunk.keywords)}")
        keyword_score = len(query_tokens & chunk_tokens) / max(1, len(query_tokens))
        vector_score = _cosine(query_embedding, chunk.embedding)
        scored.append((0.4 * keyword_score + 0.6 * max(0.0, vector_score), chunk))
    selected = sorted(scored, key=lambda pair: pair[0], reverse=True)[:top_k]

    if selected:
        overlap_conditions = [
            and_(
                VideoSegment.end_ms >= chunk.start_ms,
                VideoSegment.start_ms <= chunk.end_ms,
            )
            for _, chunk in selected
        ]
        segments = list(
            (
                await db.scalars(
                    select(VideoSegment)
                    .where(
                        VideoSegment.video_id == video_id,
                        or_(*overlap_conditions),
                    )
                    .order_by(VideoSegment.start_ms)
                )
            ).all()
        )
    else:
        segments = list(
            (
                await db.scalars(
                    select(VideoSegment)
                    .where(VideoSegment.video_id == video_id)
                    .order_by(VideoSegment.start_ms)
                    .limit(top_k * 3)
                )
            ).all()
        )

    evidence: list[RetrievedEvidence] = []
    for segment in segments:
        score = max(
            (
                chunk_score
                for chunk_score, chunk in selected
                if segment.end_ms >= chunk.start_ms and segment.start_ms <= chunk.end_ms
            ),
            default=0.0,
        )
        if segment.transcript.strip():
            evidence.append(
                RetrievedEvidence(
                    id=f"{segment.id}:ASR",
                    source="ASR",
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    content=segment.transcript.strip(),
                    score=score,
                )
            )
        if segment.visual_text.strip():
            evidence.append(
                RetrievedEvidence(
                    id=f"{segment.id}:VISION",
                    source="VISION",
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    content=segment.visual_text.strip(),
                    frame_key=segment.frame_keys[0] if segment.frame_keys else None,
                    score=score,
                )
            )
    return evidence[: top_k * 4]
