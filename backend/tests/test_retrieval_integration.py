from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agents.retrieval import hybrid_retrieve
from app.core.database import Base
from app.models.entities import SemanticChunk, Video, VideoSegment
from app.models.enums import SourceType, VideoStatus
from app.services.ai_provider import ai_provider


async def test_retrieval_does_not_load_gap_between_distant_chunks(monkeypatch) -> None:
    monkeypatch.setattr(ai_provider, "configured", False)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        video = Video(
            title="检索测试",
            source_type=SourceType.UPLOAD,
            status=VideoStatus.READY,
        )
        db.add(video)
        await db.flush()
        db.add_all(
            [
                SemanticChunk(
                    video_id=video.id,
                    start_ms=0,
                    end_ms=300_000,
                    summary="alpha 开场",
                    keywords=[],
                    embedding=[],
                ),
                SemanticChunk(
                    video_id=video.id,
                    start_ms=300_001,
                    end_ms=600_000,
                    summary="无关内容",
                    keywords=[],
                    embedding=[],
                ),
                SemanticChunk(
                    video_id=video.id,
                    start_ms=600_001,
                    end_ms=900_000,
                    summary="omega 结尾",
                    keywords=[],
                    embedding=[],
                ),
                VideoSegment(
                    video_id=video.id,
                    start_ms=10_000,
                    end_ms=20_000,
                    transcript="alpha 证据",
                ),
                VideoSegment(
                    video_id=video.id,
                    start_ms=400_000,
                    end_ms=410_000,
                    transcript="不应返回的间隔证据",
                ),
                VideoSegment(
                    video_id=video.id,
                    start_ms=700_000,
                    end_ms=710_000,
                    transcript="omega 证据",
                ),
            ]
        )
        await db.commit()

        evidence = await hybrid_retrieve(db, video.id, "alpha omega", top_k=2)

    await engine.dispose()
    contents = [item.content for item in evidence]
    assert contents == ["alpha 证据", "omega 证据"]
    assert all(item.score > 0 for item in evidence)
