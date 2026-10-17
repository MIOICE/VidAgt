from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "vidagt",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.pipeline"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 43_200},
    result_backend_transport_options={"visibility_timeout": 43_200},
    task_routes={
        "app.tasks.pipeline.import_remote_video": {"queue": "ingest"},
        "app.tasks.pipeline.process_video": {"queue": "media"},
        "app.tasks.pipeline.run_analysis": {"queue": "agent"},
    },
    timezone="Asia/Shanghai",
    enable_utc=True,
)
