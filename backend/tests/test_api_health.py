import httpx
import pytest

from app.core.database import get_db
from app.core.redis import get_redis
from app.main import app


class HealthyDatabase:
    async def execute(self, _: object) -> None:
        return None


class HealthyRedis:
    async def ping(self) -> bool:
        return True


class UnavailableRedis:
    async def ping(self) -> bool:
        raise ConnectionError("redis offline")


async def _database_override():
    yield HealthyDatabase()


async def _healthy_redis_override():
    yield HealthyRedis()


async def _unavailable_redis_override():
    yield UnavailableRedis()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as value:
        yield value
    app.dependency_overrides.clear()


async def test_live_endpoint_does_not_require_dependencies(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_endpoint_checks_database_and_redis(client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_db] = _database_override
    app.dependency_overrides[get_redis] = _healthy_redis_override

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_ready_endpoint_reports_dependency_failure(client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_db] = _database_override
    app.dependency_overrides[get_redis] = _unavailable_redis_override

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert "redis offline" in response.json()["detail"]
