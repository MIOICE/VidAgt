from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.retrieval import hybrid_retrieve
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.entities import AnalysisRun, Conversation, Message, Video
from app.models.enums import AnalysisStatus, VideoStatus
from app.schemas.analysis import (
    AnalysisCreate,
    AnalysisResponse,
    ChatHistoryMessage,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
)
from app.schemas.common import Evidence
from app.services.ai_provider import ai_provider
from app.services.rate_limit import enforce_ai_rate_limit

router = APIRouter(tags=["agent"])


def _render_recent_history(messages: list[Message], max_chars: int = 6000) -> str:
    lines = [
        f"{'用户' if message.role == 'user' else '助手'}：{message.content.strip()}"
        for message in messages
        if message.content.strip()
    ]
    history = "\n".join(lines)
    if len(history) <= max_chars:
        return history
    return f"…（较早对话已裁剪）\n{history[-max_chars:]}"


@router.post(
    "/videos/{video_id}/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_analysis(
    video_id: str,
    payload: AnalysisCreate,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> AnalysisRun:
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    if video.status != VideoStatus.READY:
        raise HTTPException(status_code=409, detail="视频尚未解析完成")
    if not ai_provider.configured:
        raise HTTPException(status_code=503, detail="AI_API_KEY 尚未配置")
    await enforce_ai_rate_limit(redis)
    analysis = AnalysisRun(
        video_id=video_id,
        goal=payload.goal,
        mode=payload.mode,
        language=payload.language,
        status=AnalysisStatus.PENDING,
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    from app.tasks.pipeline import run_analysis

    run_analysis.delay(analysis.id)
    return analysis


@router.get("/videos/{video_id}/analyses", response_model=list[AnalysisResponse])
async def list_analyses(
    video_id: str, db: AsyncSession = Depends(get_db)
) -> list[AnalysisRun]:
    return list(
        (
            await db.scalars(
                select(AnalysisRun)
                .where(AnalysisRun.video_id == video_id)
                .order_by(AnalysisRun.created_at.desc())
            )
        ).all()
    )


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: str, db: AsyncSession = Depends(get_db)
) -> AnalysisRun:
    analysis = await db.get(AnalysisRun, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return analysis


@router.get("/videos/{video_id}/chat/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    video_id: str,
    conversation_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> ChatHistoryResponse:
    if not await db.get(Video, video_id):
        raise HTTPException(status_code=404, detail="视频不存在")
    conversation = None
    if conversation_id:
        conversation = await db.get(Conversation, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        conversation = await db.scalar(
            select(Conversation)
            .where(Conversation.video_id == video_id)
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
    if not conversation:
        return ChatHistoryResponse(conversation_id=None, messages=[])
    if conversation.video_id != video_id:
        raise HTTPException(status_code=409, detail="会话不属于当前视频")

    messages = list(
        (
            await db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc())
                .limit(50)
            )
        ).all()
    )
    messages.reverse()
    return ChatHistoryResponse(
        conversation_id=conversation.id,
        messages=[ChatHistoryMessage.model_validate(message) for message in messages],
    )


@router.post("/videos/{video_id}/chat", response_model=ChatResponse)
async def chat_with_video(
    video_id: str,
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> ChatResponse:
    video = await db.get(Video, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="视频不存在")
    if video.status != VideoStatus.READY:
        raise HTTPException(status_code=409, detail="视频尚未解析完成")
    if not ai_provider.configured:
        raise HTTPException(status_code=503, detail="AI_API_KEY 尚未配置")
    await enforce_ai_rate_limit(redis)
    conversation = None
    if payload.conversation_id:
        conversation = await db.get(Conversation, payload.conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="会话不存在")
    if conversation and conversation.video_id != video_id:
        raise HTTPException(status_code=409, detail="会话不属于当前视频")
    if not conversation:
        conversation = Conversation(video_id=video_id, title=payload.question[:80])
        db.add(conversation)
        await db.flush()

    recent_messages = list(
        (
            await db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc())
                .limit(12)
            )
        ).all()
    )
    recent_messages.reverse()
    history_text = _render_recent_history(recent_messages)
    recent_user_context = " ".join(
        message.content for message in recent_messages if message.role == "user"
    )[-3000:]
    retrieval_query = f"{recent_user_context}\n{payload.question}".strip()
    evidence_items = await hybrid_retrieve(db, video_id, retrieval_query, top_k=6)
    evidence_text = "\n".join(
        f"[{item.id}] {item.start_ms}~{item.end_ms}ms {item.source}: {item.content}"
        for item in evidence_items
    )
    answer = await ai_provider.text_completion(
        "你是视频问答助手。结合对话历史理解代词和追问意图，但只能依据提供的"
        "视频证据回答事实问题；证据不足时明确说明。引用格式为[证据ID]。",
        f"最近对话：\n{history_text or '（无）'}\n\n"
        f"当前问题：{payload.question}\n\n视频证据：\n{evidence_text[:20000]}",
    )
    db.add(Message(conversation_id=conversation.id, role="user", content=payload.question))
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=answer,
        evidence=[item.model_dump() for item in evidence_items],
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)
    return ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        answer=answer,
        evidence=[Evidence(**item.model_dump(exclude={"score"})) for item in evidence_items],
    )
