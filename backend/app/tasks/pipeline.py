from __future__ import annotations

import asyncio
import mimetypes
import shutil
import tempfile
from pathlib import Path

import yt_dlp
from redis.asyncio import Redis

from app.agents.graph import invoke_analysis
from app.core.async_runner import run_async
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.time import utc_now
from app.media.pipeline import process_video_pipeline
from app.models.entities import AnalysisRun, ProcessingTask, Video
from app.models.enums import AnalysisStatus, ProcessingStage, TaskStatus, VideoStatus
from app.services.lease import LeaseUnavailable
from app.services.object_storage import object_storage
from app.services.url_safety import validate_public_http_url


@celery_app.task(bind=True, max_retries=20)
def process_video(self, video_id: str, task_id: str) -> None:
    async def run() -> None:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await process_video_pipeline(video_id, task_id, redis)
        finally:
            await redis.aclose()

    try:
        run_async(run())
    except LeaseUnavailable as exc:
        raise self.retry(exc=exc, countdown=30) from exc


@celery_app.task(bind=True, max_retries=3)
def import_remote_video(self, video_id: str, task_id: str) -> None:
    async def run() -> None:
        async with SessionLocal() as db:
            video = await db.get(Video, video_id)
            task = await db.get(ProcessingTask, task_id)
            if not video or not video.source_url or not task:
                raise RuntimeError("链接导入任务不存在")
            source_url = video.source_url
            task.status = TaskStatus.RUNNING
            task.stage = ProcessingStage.IMPORTING
            task.progress = 0.02
            task.started_at = utc_now()
            await db.commit()

        await validate_public_http_url(source_url)

        temp_dir = Path(tempfile.mkdtemp(prefix=f"vidagt-import-{video_id}-"))
        try:
            output_template = str(temp_dir / "source.%(ext)s")

            def download() -> Path:
                options = {
                    "outtmpl": output_template,
                    "noplaylist": True,
                    "restrictfilenames": True,
                    "max_filesize": settings.max_upload_bytes,
                    "quiet": True,
                    "no_warnings": True,
                }
                with yt_dlp.YoutubeDL(options) as downloader:
                    info = downloader.extract_info(source_url, download=True)
                    return Path(downloader.prepare_filename(info))

            source = await asyncio.to_thread(download)
            if source.stat().st_size > settings.max_upload_bytes:
                raise ValueError("远程视频超过 2GB 限制")
            object_key = f"imports/{video_id}/source{source.suffix.lower()}"
            mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            await object_storage.upload_file(source, object_key, mime_type)
            async with SessionLocal() as db:
                video = await db.get(Video, video_id)
                if video:
                    video.object_key = object_key
                    video.mime_type = mime_type
                    video.size_bytes = source.stat().st_size
                    await db.commit()
            process_video.delay(video_id, task_id)
        finally:
            await asyncio.to_thread(shutil.rmtree, temp_dir, True)

    try:
        run_async(run())
    except Exception as exc:
        error = str(exc)[:4000]

        async def mark_failed() -> None:
            async with SessionLocal() as db:
                video = await db.get(Video, video_id)
                task = await db.get(ProcessingTask, task_id)
                if video:
                    video.status = VideoStatus.FAILED
                    video.error = error
                if task:
                    task.status = TaskStatus.FAILED
                    task.error = error
                    task.finished_at = utc_now()
                await db.commit()

        run_async(mark_failed())
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 5) from exc


@celery_app.task(bind=True, max_retries=3)
def run_analysis(self, analysis_id: str) -> None:
    async def run() -> None:
        async with SessionLocal() as db:
            analysis = await db.get(AnalysisRun, analysis_id)
            if not analysis:
                raise RuntimeError("分析任务不存在")
            analysis.status = AnalysisStatus.RUNNING
            analysis.progress = 0.1
            await db.commit()
            await db.refresh(analysis)
        report = await invoke_analysis(analysis)
        async with SessionLocal() as db:
            analysis = await db.get(AnalysisRun, analysis_id)
            if analysis:
                analysis.report = report
                analysis.progress = 1.0
                analysis.status = AnalysisStatus.COMPLETED
                analysis.error = None
                await db.commit()

    try:
        run_async(run())
    except Exception as exc:
        error = str(exc)[:4000]

        async def mark_failed() -> None:
            async with SessionLocal() as db:
                analysis = await db.get(AnalysisRun, analysis_id)
                if analysis:
                    analysis.status = AnalysisStatus.FAILED
                    analysis.error = error
                    await db.commit()

        run_async(mark_failed())
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 10) from exc
