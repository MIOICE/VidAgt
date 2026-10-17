from __future__ import annotations

import asyncio
import shutil
import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import utc_now
from app.media.tools import (
    extract_audio,
    extract_keyframes,
    probe_video,
    sha256_file,
    transcode_preview,
    transcribe_audio,
)
from app.models.entities import (
    AnalysisRun,
    Keyframe,
    ProcessingTask,
    SemanticChunk,
    Video,
    VideoSegment,
)
from app.models.enums import AnalysisStatus, ProcessingStage, TaskStatus, VideoStatus
from app.services.ai_provider import ai_provider
from app.services.lease import RedisLease
from app.services.object_storage import object_storage


async def set_task_state(
    task_id: str,
    stage: ProcessingStage,
    progress: float,
    status: TaskStatus = TaskStatus.RUNNING,
    error: str | None = None,
) -> None:
    async with SessionLocal() as db:
        task = await db.get(ProcessingTask, task_id)
        if task:
            task.stage = stage
            task.progress = progress
            task.status = status
            task.error = error
            if status == TaskStatus.RUNNING and task.started_at is None:
                task.started_at = utc_now()
            if status in {TaskStatus.COMPLETED, TaskStatus.FAILED}:
                task.finished_at = utc_now()
            await db.commit()


async def _reuse_context(current: Video, existing: Video, task_id: str) -> bool:
    async with SessionLocal() as db:
        source_segments = list(
            (
                await db.scalars(
                    select(VideoSegment).where(VideoSegment.video_id == existing.id)
                )
            ).all()
        )
        source_chunks = list(
            (
                await db.scalars(
                    select(SemanticChunk).where(SemanticChunk.video_id == existing.id)
                )
            ).all()
        )
        source_frames = list(
            (await db.scalars(select(Keyframe).where(Keyframe.video_id == existing.id))).all()
        )
        target = await db.get(Video, current.id)
        if not target:
            return False
        for item in source_segments:
            db.add(
                VideoSegment(
                    video_id=target.id,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    transcript=item.transcript,
                    visual_text=item.visual_text,
                    frame_keys=item.frame_keys,
                )
            )
        for item in source_chunks:
            db.add(
                SemanticChunk(
                    video_id=target.id,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    summary=item.summary,
                    keywords=item.keywords,
                    embedding=item.embedding,
                )
            )
        for item in source_frames:
            db.add(
                Keyframe(
                    video_id=target.id,
                    timestamp_ms=item.timestamp_ms,
                    object_key=item.object_key,
                    description=item.description,
                    scene_score=item.scene_score,
                )
            )
        target.duration_ms = existing.duration_ms
        target.preview_key = existing.preview_key
        target.media_metadata = {**existing.media_metadata, "deduplicated_from": existing.id}
        target.status = VideoStatus.READY
        await db.commit()
    await set_task_state(task_id, ProcessingStage.COMPLETED, 1.0, TaskStatus.COMPLETED)
    return True


def _fuse_segments(
    duration_ms: int,
    transcript: list[dict[str, Any]],
    frames: list[tuple[int, str, str]],
) -> list[dict[str, Any]]:
    window_ms = 30_000
    windows: list[dict[str, Any]] = []
    for start in range(0, max(duration_ms, 1), window_ms):
        end = min(start + window_ms, duration_ms)
        speech = " ".join(
            item["text"]
            for item in transcript
            if item["end_ms"] >= start and item["start_ms"] < end
        ).strip()
        matching_frames = [item for item in frames if start <= item[0] < end]
        visual = "\n".join(item[2] for item in matching_frames if item[2]).strip()
        if speech or visual or matching_frames:
            windows.append(
                {
                    "start_ms": start,
                    "end_ms": end,
                    "transcript": speech,
                    "visual_text": visual,
                    "frame_keys": [item[1] for item in matching_frames],
                }
            )
    return windows


async def _build_chunks(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index in range(0, len(segments), 10):
        group = segments[index : index + 10]
        if not group:
            continue
        raw = "\n".join(
            f"[{item['start_ms']}ms] ASR:{item['transcript']} VISION:{item['visual_text']}"
            for item in group
        )
        if ai_provider.configured:
            summary = await ai_provider.text_completion(
                "将视频片段压缩成不超过200字的事实摘要，并在末尾给出5个关键词。",
                raw[:18000],
            )
        else:
            summary = raw[:1000]
        results.append(
            {
                "start_ms": group[0]["start_ms"],
                "end_ms": group[-1]["end_ms"],
                "summary": summary,
                "keywords": [],
            }
        )
    if ai_provider.configured and results:
        embeddings = await ai_provider.embed_documents([item["summary"] for item in results])
        for item, embedding in zip(results, embeddings, strict=True):
            item["embedding"] = embedding
    else:
        for item in results:
            item["embedding"] = []
    return results


async def process_video_pipeline(video_id: str, task_id: str, redis: Redis) -> None:
    workspace = settings.work_dir / f"video-{video_id}-{uuid.uuid4().hex[:8]}"
    workspace.mkdir(parents=True, exist_ok=True)
    try:
        async with SessionLocal() as db:
            video = await db.get(Video, video_id)
            if not video or not video.object_key:
                raise RuntimeError("视频或对象存储路径不存在")
            video.status = VideoStatus.PROCESSING
            await db.commit()
            source = workspace / video.object_key.rsplit("/", 1)[-1]
        await object_storage.download_file(video.object_key, source)

        await set_task_state(task_id, ProcessingStage.PROBING, 0.08)
        metadata = await probe_video(source)
        if metadata["duration_ms"] > settings.max_video_duration_seconds * 1000:
            raise ValueError("视频时长超过 3 小时限制")

        await set_task_state(task_id, ProcessingStage.HASHING, 0.12)
        digest = await sha256_file(source)
        async with RedisLease(redis, f"vidagt:lock:content:{digest}"):
            async with SessionLocal() as db:
                current = await db.get(Video, video_id)
                existing = await db.scalar(
                    select(Video).where(
                        Video.sha256 == digest,
                        Video.id != video_id,
                        Video.status == VideoStatus.READY,
                    )
                )
                if current is None:
                    raise RuntimeError("视频记录不存在")
                if existing and await _reuse_context(current, existing, task_id):
                    return

            await set_task_state(task_id, ProcessingStage.TRANSCODING, 0.2)
            preview = workspace / "preview.mp4"
            await transcode_preview(source, preview)
            preview_key = f"videos/{video_id}/preview.mp4"
            await object_storage.upload_file(preview, preview_key, "video/mp4")

            await set_task_state(task_id, ProcessingStage.AUDIO, 0.32)
            audio = workspace / "audio.wav"
            await extract_audio(source, audio)
            await set_task_state(task_id, ProcessingStage.ASR, 0.42)
            transcript = await transcribe_audio(audio)

            await set_task_state(task_id, ProcessingStage.KEYFRAMES, 0.62)
            frame_files = await extract_keyframes(
                source, workspace / "frames", metadata["duration_ms"]
            )
            uploaded_frames: list[tuple[int, str, str, float]] = []
            vision_stride = max(1, len(frame_files) // max(1, settings.max_vision_frames))
            for index, (timestamp_ms, frame_path, score) in enumerate(frame_files):
                object_key = f"videos/{video_id}/frames/{frame_path.name}"
                await object_storage.upload_file(frame_path, object_key, "image/jpeg")
                description = ""
                if ai_provider.configured and index % vision_stride == 0:
                    progress = 0.68 + index / max(1, len(frame_files)) * 0.08
                    await set_task_state(task_id, ProcessingStage.VISION, progress)
                    description = await ai_provider.describe_image(frame_path, timestamp_ms)
                uploaded_frames.append((timestamp_ms, object_key, description, score))

            await set_task_state(task_id, ProcessingStage.FUSION, 0.78)
            segments = _fuse_segments(
                metadata["duration_ms"],
                transcript,
                [(item[0], item[1], item[2]) for item in uploaded_frames],
            )
            chunks = await _build_chunks(segments)

            await set_task_state(task_id, ProcessingStage.INDEXING, 0.9)
            async with SessionLocal() as db:
                await db.execute(delete(VideoSegment).where(VideoSegment.video_id == video_id))
                await db.execute(delete(SemanticChunk).where(SemanticChunk.video_id == video_id))
                await db.execute(delete(Keyframe).where(Keyframe.video_id == video_id))
                for item in segments:
                    db.add(VideoSegment(video_id=video_id, **item))
                for item in chunks:
                    db.add(SemanticChunk(video_id=video_id, **item))
                for timestamp_ms, object_key, description, score in uploaded_frames:
                    db.add(
                        Keyframe(
                            video_id=video_id,
                            timestamp_ms=timestamp_ms,
                            object_key=object_key,
                            description=description,
                            scene_score=score,
                        )
                    )
                video = await db.get(Video, video_id)
                if video:
                    video.sha256 = digest
                    video.duration_ms = metadata["duration_ms"]
                    video.preview_key = preview_key
                    video.media_metadata = metadata
                    video.status = VideoStatus.READY
                    video.error = None
                await db.commit()

            await set_task_state(task_id, ProcessingStage.COMPLETED, 1.0, TaskStatus.COMPLETED)
            if ai_provider.configured:
                async with SessionLocal() as db:
                    analysis = AnalysisRun(
                        video_id=video_id,
                        goal="生成结构化视频报告，包含摘要、章节、关键结论和行动建议。",
                        mode="AUTO_REPORT",
                        status=AnalysisStatus.PENDING,
                    )
                    db.add(analysis)
                    await db.commit()
                    await db.refresh(analysis)
                from app.tasks.pipeline import run_analysis

                run_analysis.delay(analysis.id)
    except Exception as exc:
        async with SessionLocal() as db:
            video = await db.get(Video, video_id)
            if video:
                video.status = VideoStatus.FAILED
                video.error = str(exc)[:4000]
                await db.commit()
        await set_task_state(
            task_id, ProcessingStage.QUEUED, 0.0, TaskStatus.FAILED, str(exc)[:4000]
        )
        raise
    finally:
        await asyncio.to_thread(shutil.rmtree, workspace, True)
