from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_PATH = Path(__file__).resolve()
_ENV_FILES = (
    str(_CONFIG_PATH.parents[3] / ".env"),
    str(_CONFIG_PATH.parents[2] / ".env"),
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "VidAgt"
    app_env: str = "development"
    app_debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    auto_create_tables: bool = True

    database_url: str = "mysql+asyncmy://vidagt:vidagt@localhost:3306/vidagt?charset=utf8mb4"
    redis_url: str = "redis://localhost:6379/3"
    redis_search_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    minio_endpoint: str = "http://localhost:9000"
    minio_public_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "vidagt"
    presigned_url_ttl_seconds: int = 900

    max_upload_bytes: int = 2 * 1024 * 1024 * 1024
    max_video_duration_seconds: int = 3 * 60 * 60
    upload_part_size: int = 16 * 1024 * 1024
    upload_parallelism: int = 4
    work_dir: Path = Path("/tmp/vidagt")
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    asr_model_gpu: str = "large-v3-turbo"
    asr_model_cpu: str = "small"
    asr_device: str = "auto"
    asr_compute_type_gpu: str = "int8_float16"
    asr_compute_type_cpu: str = "int8"
    max_keyframes: int = 180
    max_vision_frames: int = 40

    ai_api_key: str = ""
    ai_base_url: str = "https://api.siliconflow.cn/v1"
    llm_model: str = "deepseek-ai/DeepSeek-V3.2"
    vision_model: str = "Qwen/Qwen3-VL-30B-A3B-Instruct"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024
    ai_requests_per_minute: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
