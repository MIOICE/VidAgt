from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from pydantic import BaseModel
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from app.core.config import settings

ModelT = TypeVar("ModelT", bound=BaseModel)
TRANSIENT_AI_ERRORS = (
    TimeoutError,
    ConnectionError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)


def _model_extra_body(model: str) -> dict[str, bool] | None:
    if model.startswith("Qwen/Qwen3") or model.lower().startswith("qwen3"):
        return {"enable_thinking": False}
    return None


def _retry_transient_ai():
    return retry(
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(multiplier=1, max=30),
        retry=retry_if_exception_type(TRANSIENT_AI_ERRORS),
        reraise=True,
    )


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("model response must be a JSON object")
    return value


class AIProvider:
    def __init__(self) -> None:
        self.configured = bool(settings.ai_api_key)
        self._chat: ChatOpenAI | None = None
        self._vision: ChatOpenAI | None = None
        self._embeddings: OpenAIEmbeddings | None = None

    def _require_key(self) -> None:
        if not self.configured:
            raise RuntimeError("AI_API_KEY 未配置，无法调用模型。")

    @property
    def chat(self) -> ChatOpenAI:
        self._require_key()
        if self._chat is None:
            self._chat = ChatOpenAI(
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
                model=settings.llm_model,
                temperature=0.1,
                timeout=120,
                max_retries=0,
                extra_body=_model_extra_body(settings.llm_model),
            )
        return self._chat

    @property
    def vision(self) -> ChatOpenAI:
        self._require_key()
        if self._vision is None:
            self._vision = ChatOpenAI(
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
                model=settings.vision_model,
                temperature=0,
                timeout=120,
                max_retries=0,
                extra_body=_model_extra_body(settings.vision_model),
            )
        return self._vision

    @property
    def embeddings(self) -> OpenAIEmbeddings:
        self._require_key()
        if self._embeddings is None:
            self._embeddings = OpenAIEmbeddings(
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
                model=settings.embedding_model,
                dimensions=settings.embedding_dimension,
                check_embedding_ctx_length=False,
                max_retries=0,
            )
        return self._embeddings

    @_retry_transient_ai()
    async def json_completion(
        self, schema: type[ModelT], system_prompt: str, user_prompt: str
    ) -> ModelT:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        response = await self.chat.ainvoke(
            [
                SystemMessage(
                    content=(
                        f"{system_prompt}\n只输出一个合法 JSON 对象，不要输出 Markdown。"
                        f"输出必须符合此 JSON Schema：{schema_json}"
                    )
                ),
                HumanMessage(content=user_prompt),
            ]
        )
        return schema.model_validate(_extract_json(str(response.content)))

    @_retry_transient_ai()
    async def text_completion(self, system_prompt: str, user_prompt: str) -> str:
        response = await self.chat.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        return str(response.content)

    @_retry_transient_ai()
    async def describe_image(self, image_path: Path, timestamp_ms: int) -> str:
        mime = "image/jpeg" if image_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        image_bytes = await asyncio.to_thread(image_path.read_bytes)
        encoded = base64.b64encode(image_bytes).decode("ascii")
        response = await self.vision.ainvoke(
            [
                SystemMessage(
                    content="你是视频画面分析器。简洁描述画面中的人物、动作、场景和可见文字。"
                ),
                HumanMessage(
                    content=[
                        {
                            "type": "text",
                            "text": f"这是视频 {timestamp_ms / 1000:.1f} 秒的关键帧。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ]
                ),
            ]
        )
        return str(response.content).strip()

    @_retry_transient_ai()
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self.embeddings.aembed_documents(texts)

    @_retry_transient_ai()
    async def embed_query(self, text: str) -> list[float]:
        return await self.embeddings.aembed_query(text)


ai_provider = AIProvider()
