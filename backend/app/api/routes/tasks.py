from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.database import SessionLocal, get_db
from app.models.entities import ProcessingTask
from app.schemas.common import TaskResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])
FINAL_STATES = {"COMPLETED", "FAILED"}


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)) -> ProcessingTask:
    task = await db.get(ProcessingTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{task_id}/events")
async def task_events(task_id: str) -> EventSourceResponse:
    async def stream():
        previous = ""
        while True:
            async with SessionLocal() as db:
                task = await db.get(ProcessingTask, task_id)
                if task is None:
                    yield {"event": "error", "data": json.dumps({"detail": "任务不存在"})}
                    break
                payload = TaskResponse.model_validate(task).model_dump(mode="json")
                serialized = json.dumps(payload, ensure_ascii=False)
                if serialized != previous:
                    yield {"event": "progress", "data": serialized}
                    previous = serialized
                if task.status in FINAL_STATES:
                    yield {"event": "done", "data": serialized}
                    break
            await asyncio.sleep(1)

    return EventSourceResponse(stream(), ping=15)

