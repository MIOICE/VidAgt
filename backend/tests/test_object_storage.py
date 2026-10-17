from unittest.mock import MagicMock

from botocore.exceptions import ClientError

from app.core.config import settings
from app.services.object_storage import ObjectStorage


def test_ensure_bucket_keeps_existing_bucket_and_applies_cors() -> None:
    storage = ObjectStorage.__new__(ObjectStorage)
    storage.client = MagicMock()
    storage.bucket = "videos"

    storage._ensure_bucket_sync()

    storage.client.head_bucket.assert_called_once_with(Bucket="videos")
    storage.client.create_bucket.assert_not_called()
    storage.client.put_bucket_cors.assert_called_once()
    cors = storage.client.put_bucket_cors.call_args.kwargs["CORSConfiguration"]
    rule = cors["CORSRules"][0]
    assert rule["AllowedOrigins"] == settings.cors_origin_list
    assert rule["ExposeHeaders"] == ["ETag"]


def test_ensure_bucket_creates_missing_bucket_before_applying_cors() -> None:
    storage = ObjectStorage.__new__(ObjectStorage)
    storage.client = MagicMock()
    storage.client.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}},
        "HeadBucket",
    )
    storage.bucket = "videos"

    storage._ensure_bucket_sync()

    storage.client.create_bucket.assert_called_once_with(Bucket="videos")
    storage.client.put_bucket_cors.assert_called_once()


def test_ensure_bucket_accepts_storage_without_bucket_cors_api() -> None:
    storage = ObjectStorage.__new__(ObjectStorage)
    storage.client = MagicMock()
    storage.client.put_bucket_cors.side_effect = ClientError(
        {"Error": {"Code": "NotImplemented", "Message": "Not implemented"}},
        "PutBucketCors",
    )
    storage.bucket = "videos"

    storage._ensure_bucket_sync()

    storage.client.head_bucket.assert_called_once_with(Bucket="videos")
    storage.client.create_bucket.assert_not_called()
