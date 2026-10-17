from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class ObjectStorage:
    def __init__(self) -> None:
        common: dict[str, Any] = {
            "aws_access_key_id": settings.minio_access_key,
            "aws_secret_access_key": settings.minio_secret_key,
            "region_name": "us-east-1",
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self.client = boto3.client("s3", endpoint_url=settings.minio_endpoint, **common)
        self.public_client = boto3.client(
            "s3", endpoint_url=settings.minio_public_endpoint, **common
        )
        self.bucket = settings.minio_bucket

    def _ensure_bucket_sync(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

        # Keep browser multipart uploads self-healing without relying on a
        # separate MinIO Client image. Reapplying this configuration is
        # idempotent and also picks up CORS_ORIGINS changes after restart.
        try:
            self.client.put_bucket_cors(
                Bucket=self.bucket,
                CORSConfiguration={
                    "CORSRules": [
                        {
                            "AllowedHeaders": ["*"],
                            "AllowedMethods": [
                                "GET",
                                "PUT",
                                "POST",
                                "DELETE",
                                "HEAD",
                            ],
                            "AllowedOrigins": settings.cors_origin_list,
                            "ExposeHeaders": ["ETag"],
                            "MaxAgeSeconds": 3600,
                        }
                    ]
                },
            )
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code != "NotImplemented":
                raise
            logger.warning(
                "Object storage does not implement PutBucketCors; "
                "using server-level CORS configuration"
            )

    async def ensure_bucket(self) -> None:
        await asyncio.to_thread(self._ensure_bucket_sync)

    async def create_multipart(self, object_key: str, content_type: str) -> str:
        response = await asyncio.to_thread(
            self.client.create_multipart_upload,
            Bucket=self.bucket,
            Key=object_key,
            ContentType=content_type,
        )
        return str(response["UploadId"])

    async def sign_upload_part(
        self, object_key: str, multipart_id: str, part_number: int
    ) -> str:
        return await asyncio.to_thread(
            self.public_client.generate_presigned_url,
            "upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": object_key,
                "UploadId": multipart_id,
                "PartNumber": part_number,
            },
            ExpiresIn=settings.presigned_url_ttl_seconds,
        )

    async def list_parts(self, object_key: str, multipart_id: str) -> list[dict[str, Any]]:
        def _list() -> list[dict[str, Any]]:
            parts: list[dict[str, Any]] = []
            marker = 0
            while True:
                response = self.client.list_parts(
                    Bucket=self.bucket,
                    Key=object_key,
                    UploadId=multipart_id,
                    PartNumberMarker=marker,
                )
                parts.extend(response.get("Parts", []))
                if not response.get("IsTruncated"):
                    break
                marker = int(response["NextPartNumberMarker"])
            return parts

        return await asyncio.to_thread(_list)

    async def complete_multipart(
        self, object_key: str, multipart_id: str, parts: list[dict[str, Any]]
    ) -> None:
        await asyncio.to_thread(
            self.client.complete_multipart_upload,
            Bucket=self.bucket,
            Key=object_key,
            UploadId=multipart_id,
            MultipartUpload={"Parts": parts},
        )

    async def abort_multipart(self, object_key: str, multipart_id: str) -> None:
        await asyncio.to_thread(
            self.client.abort_multipart_upload,
            Bucket=self.bucket,
            Key=object_key,
            UploadId=multipart_id,
        )

    async def upload_file(
        self, source: Path, object_key: str, content_type: str = "application/octet-stream"
    ) -> None:
        await asyncio.to_thread(
            self.client.upload_file,
            str(source),
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )

    async def download_file(self, object_key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            self.client.download_file, self.bucket, object_key, str(destination)
        )

    async def sign_download(self, object_key: str) -> str:
        return await asyncio.to_thread(
            self.public_client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": object_key},
            ExpiresIn=settings.presigned_url_ttl_seconds,
        )

    async def delete_objects(self, object_keys: list[str]) -> None:
        keys = sorted({key for key in object_keys if key})
        if not keys:
            return
        await asyncio.to_thread(
            self.client.delete_objects,
            Bucket=self.bucket,
            Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
        )


object_storage = ObjectStorage()
