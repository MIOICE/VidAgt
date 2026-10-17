from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services.rate_limit import enforce_ai_rate_limit


async def test_token_bucket_allows_request() -> None:
    redis = AsyncMock()
    redis.eval.return_value = 1

    await enforce_ai_rate_limit(redis, bucket="analysis")

    args = redis.eval.await_args.args
    assert args[1] == 1
    assert args[2] == "vidagt:rate:ai:analysis"


async def test_token_bucket_rejects_when_empty() -> None:
    redis = AsyncMock()
    redis.eval.return_value = 0

    with pytest.raises(HTTPException) as exc_info:
        await enforce_ai_rate_limit(redis)

    assert exc_info.value.status_code == 429
