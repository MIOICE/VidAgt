from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import Keyframe, ProcessingTask, Video, VideoSegment
from app.models.enums import SourceType, TaskStatus, VideoStatus
from app.schemas.common import TaskResponse
from app.schemas.upload import ImportUrlRequest
from app.schemas.video import PlaybackResponse, SegmentResponse, VideoListResponse, VideoResponse
from app.services.object_storage import object_storage
from app.services.url_safety import UnsafeUrlError, validate_public_http_url

router = APIRouter(prefix="/videos", tags=["videos"])


async def _get_video(video_id: str, db: AsyncSession) -> Video:
    video = await db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="视频不存在")
    return video


@router.get("", response_model=VideoListResponse)
async def list_videos(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> VideoListResponse:
    total = int(await db.scalar(select(func.count()).select_from(Video)) or 0)
    items = list(
        (
            await db.scalars(
                select(Video).order_by(Video.created_at.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
    return VideoListResponse(
        items=[VideoResponse.model_validate(item) for item in items], total=total
    )


@router.post("/import", response_model=TaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def import_video(
    payload: ImportUrlRequest, db: AsyncSession = Depends(get_db)
) -> ProcessingTask:
    url = str(payload.url)
    try:
        await validate_public_http_url(url)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    video = Video(
        title=payload.title or payload.url.host or "远程视频",
        source_type=SourceType.URL,
        source_url=url,
        status=VideoStatus.QUEUED,
    )
    db.add(video)
    await db.flush()
    task = ProcessingTask(video_id=video.id, kind="IMPORT", status=TaskStatus.PENDING)
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from app.tasks.pipeline import import_remote_video

    result = import_remote_video.delay(video.id, task.id)
    task.celery_task_id = result.id
    await db.commit()
    return task


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)) -> Video:
    return await _get_video(video_id, db)


@router.get("/{video_id}/playback", response_model=PlaybackResponse)
async def get_playback(video_id: str, db: AsyncSession = Depends(get_db)) -> PlaybackResponse:
    video = await _get_video(video_id, db)
    object_key = video.preview_key or video.object_key
    if not object_key:
        raise HTTPException(status_code=409, detail="视频文件尚未准备完成")
    return PlaybackResponse(
        url=await object_storage.sign_download(object_key),
        expires_in=settings.presigned_url_ttl_seconds,
    )


@router.get("/{video_id}/segments", response_model=list[SegmentResponse])
async def list_segments(
    video_id: str, db: AsyncSession = Depends(get_db)
) -> list[VideoSegment]:
    await _get_video(video_id, db)
    return list(
        (
            await db.scalars(
                select(VideoSegment)
                .where(VideoSegment.video_id == video_id)
                .order_by(VideoSegment.start_ms)
            )
        ).all()
    )


@router.post("/{video_id}/process", response_model=TaskResponse, status_code=202)
async def retry_processing(video_id: str, db: AsyncSession = Depends(get_db)) -> ProcessingTask:
    video = await _get_video(video_id, db)
    active = await db.scalar(
        select(ProcessingTask).where(
            ProcessingTask.video_id == video_id,
            ProcessingTask.status.in_(
                [TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.RETRYING]
            ),
        )
    )
    if active:
        return active
    retry_import = bool(
        not video.object_key and video.source_type == SourceType.URL and video.source_url
    )
    if not video.object_key and not retry_import:
        raise HTTPException(status_code=409, detail="源视频尚未准备完成，无法重试")
    video.status = VideoStatus.QUEUED
    video.error = None
    task = ProcessingTask(video_id=video.id, kind="IMPORT" if retry_import else "PROCESS")
    db.add(task)
    await db.commit()
    await db.refresh(task)
    if retry_import:
        from app.tasks.pipeline import import_remote_video

        result = import_remote_video.delay(video.id, task.id)
    else:
        from app.tasks.pipeline import process_video

        result = process_video.delay(video.id, task.id)
    task.celery_task_id = result.id
    await db.commit()
    return task


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(video_id: str, db: AsyncSession = Depends(get_db)) -> None:
    video = await _get_video(video_id, db)
    frame_keys = list(
        (await db.scalars(select(Keyframe.object_key).where(Keyframe.video_id == video_id))).all()
    )
    shared_frame_keys: set[str] = set()
    if frame_keys:
        shared_frame_keys = set(
            (
                await db.scalars(
                    select(Keyframe.object_key).where(
                        Keyframe.video_id != video_id, Keyframe.object_key.in_(frame_keys)
                    )
                )
            ).all()
        )
    keys_to_delete = [video.object_key] if video.object_key else []
    if video.preview_key:
        preview_shared = await db.scalar(
            select(func.count())
            .select_from(Video)
            .where(Video.id != video_id, Video.preview_key == video.preview_key)
        )
        if not preview_shared:
            keys_to_delete.append(video.preview_key)
    keys_to_delete.extend(key for key in frame_keys if key not in shared_frame_keys)
    await db.delete(video)
    await db.commit()
    await object_storage.delete_objects(keys_to_delete)
