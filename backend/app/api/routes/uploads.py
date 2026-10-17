from __future__ import annotations

import math
import uuid
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import ProcessingTask, UploadSession, Video
from app.models.enums import SourceType, UploadStatus, VideoStatus
from app.schemas.common import TaskResponse
from app.schemas.upload import (
    CompletedPart,
    PartSignRequest,
    PartSignResponse,
    SignedPart,
    UploadCompleteRequest,
    UploadCreate,
    UploadCreated,
    UploadStatusResponse,
)
from app.services.object_storage import object_storage

router = APIRouter(prefix="/uploads", tags=["uploads"])


async def _get_upload(upload_id: str, db: AsyncSession) -> UploadSession:
    upload = await db.get(UploadSession, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="上传会话不存在")
    return upload


@router.post("", response_model=UploadCreated, status_code=status.HTTP_201_CREATED)
async def create_upload(payload: UploadCreate, db: AsyncSession = Depends(get_db)) -> UploadCreated:
    if payload.size_bytes > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="文件超过 2GB 限制")
    existing = await db.scalar(
        select(UploadSession)
        .where(
            UploadSession.fingerprint == payload.fingerprint,
            UploadSession.size_bytes == payload.size_bytes,
            UploadSession.status.in_([UploadStatus.CREATED, UploadStatus.UPLOADING]),
        )
        .order_by(UploadSession.created_at.desc())
    )
    if existing:
        return UploadCreated(
            upload_id=existing.id,
            part_size=existing.part_size,
            part_count=math.ceil(existing.size_bytes / existing.part_size),
            parallelism=settings.upload_parallelism,
        )

    upload_id = str(uuid.uuid4())
    safe_name = PurePath(payload.filename).name
    suffix = PurePath(safe_name).suffix.lower()[:16]
    object_key = f"uploads/{upload_id}/source{suffix}"
    multipart_id = await object_storage.create_multipart(object_key, payload.mime_type)
    upload = UploadSession(
        id=upload_id,
        filename=safe_name,
        size_bytes=payload.size_bytes,
        mime_type=payload.mime_type,
        fingerprint=payload.fingerprint,
        object_key=object_key,
        multipart_id=multipart_id,
        part_size=settings.upload_part_size,
        status=UploadStatus.UPLOADING,
    )
    db.add(upload)
    await db.commit()
    return UploadCreated(
        upload_id=upload.id,
        part_size=upload.part_size,
        part_count=math.ceil(upload.size_bytes / upload.part_size),
        parallelism=settings.upload_parallelism,
    )


@router.get("/{upload_id}", response_model=UploadStatusResponse)
async def get_upload_status(
    upload_id: str, db: AsyncSession = Depends(get_db)
) -> UploadStatusResponse:
    upload = await _get_upload(upload_id, db)
    part_count = math.ceil(upload.size_bytes / upload.part_size)
    completed: list[CompletedPart] = []
    if upload.status != UploadStatus.COMPLETED:
        remote_parts = await object_storage.list_parts(upload.object_key, upload.multipart_id)
        completed = [
            CompletedPart(part_number=int(part["PartNumber"]), etag=str(part["ETag"]).strip('"'))
            for part in remote_parts
        ]
    completed_numbers = {part.part_number for part in completed}
    return UploadStatusResponse(
        upload_id=upload.id,
        status=upload.status,
        completed_parts=completed,
        missing_parts=[
            number for number in range(1, part_count + 1) if number not in completed_numbers
        ],
    )


@router.post("/{upload_id}/parts/sign", response_model=PartSignResponse)
async def sign_parts(
    upload_id: str, payload: PartSignRequest, db: AsyncSession = Depends(get_db)
) -> PartSignResponse:
    upload = await _get_upload(upload_id, db)
    if upload.status == UploadStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="上传已完成")
    part_count = math.ceil(upload.size_bytes / upload.part_size)
    unique_numbers = sorted(set(payload.part_numbers))
    if any(number < 1 or number > part_count for number in unique_numbers):
        raise HTTPException(status_code=422, detail="分片编号超出范围")
    parts = [
        SignedPart(
            part_number=number,
            url=await object_storage.sign_upload_part(
                upload.object_key, upload.multipart_id, number
            ),
        )
        for number in unique_numbers
    ]
    return PartSignResponse(parts=parts, expires_in=settings.presigned_url_ttl_seconds)


@router.post("/{upload_id}/complete", response_model=TaskResponse)
async def complete_upload(
    upload_id: str, payload: UploadCompleteRequest, db: AsyncSession = Depends(get_db)
) -> ProcessingTask:
    upload = await _get_upload(upload_id, db)
    if upload.status == UploadStatus.COMPLETED and upload.video_id:
        task = await db.scalar(
            select(ProcessingTask)
            .where(ProcessingTask.video_id == upload.video_id)
            .order_by(ProcessingTask.created_at.desc())
        )
        if task:
            return task
    parts = [
        {"PartNumber": item.part_number, "ETag": item.etag}
        for item in sorted(payload.parts, key=lambda item: item.part_number)
    ]
    await object_storage.complete_multipart(upload.object_key, upload.multipart_id, parts)
    video = Video(
        title=upload.filename,
        source_type=SourceType.UPLOAD,
        object_key=upload.object_key,
        mime_type=upload.mime_type,
        size_bytes=upload.size_bytes,
        status=VideoStatus.QUEUED,
    )
    db.add(video)
    await db.flush()
    task = ProcessingTask(video_id=video.id, kind="PROCESS")
    db.add(task)
    upload.status = UploadStatus.COMPLETED
    upload.video_id = video.id
    await db.commit()
    await db.refresh(task)

    from app.tasks.pipeline import process_video

    result = process_video.delay(video.id, task.id)
    task.celery_task_id = result.id
    await db.commit()
    return task
