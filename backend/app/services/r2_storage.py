"""Cloudflare R2 source-video storage over its S3-compatible API."""

from __future__ import annotations

import logging
import mimetypes
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from botocore.config import Config
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig

from ..config import UPLOAD_DIR
from .storage import (
    LocalStorageBackend,
    StorageError,
    StorageObjectNotFound,
    validate_storage_key,
)


logger = logging.getLogger(__name__)
_MULTIPART_THRESHOLD = 8 * 1024 * 1024


def _is_not_found(error: ClientError) -> bool:
    response = error.response
    code = str(response.get("Error", {}).get("Code", ""))
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"404", "NoSuchKey", "NotFound"} or status == 404


class CloudflareR2StorageBackend:
    """Persist uploaded videos in a private R2 bucket and materialize for analysis."""

    def __init__(
        self,
        client,
        bucket_name: str,
        upload_dir: str | Path,
        frames_dir: str | Path,
    ):
        self._client = client
        self.bucket_name = bucket_name
        self._local = LocalStorageBackend(upload_dir, frames_dir)
        self._transfer_config = TransferConfig(
            multipart_threshold=_MULTIPART_THRESHOLD,
            multipart_chunksize=_MULTIPART_THRESHOLD,
            max_concurrency=1,
            use_threads=False,
        )

    @classmethod
    def from_config(
        cls,
        *,
        upload_dir: str | Path,
        frames_dir: str | Path,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
    ) -> CloudflareR2StorageBackend:
        missing = [
            name
            for name, value in (
                ("R2_ACCOUNT_ID", account_id),
                ("R2_ACCESS_KEY_ID", access_key_id),
                ("R2_SECRET_ACCESS_KEY", secret_access_key),
                ("R2_BUCKET_NAME", bucket_name),
            )
            if not value
        ]
        if missing:
            raise StorageError(
                "R2 storage is selected but required environment configuration is missing."
            )

        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                max_pool_connections=2,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        return cls(client, bucket_name, upload_dir, frames_dir)

    def save_stream(self, source: BinaryIO, key: str) -> str:
        object_key = validate_storage_key(key)
        try:
            source.seek(0)
            content_type = mimetypes.guess_type(object_key)[0] or "application/octet-stream"
            self._client.upload_fileobj(
                source,
                self.bucket_name,
                object_key,
                ExtraArgs={"ContentType": content_type},
                Config=self._transfer_config,
            )
            return object_key
        except Exception as error:
            logger.error(
                "R2 video upload failed error_type=%s",
                type(error).__name__,
            )
            raise StorageError("Unable to store video.") from error

    def save_file(self, source_path: str | Path, key: str) -> str:
        with open(source_path, "rb") as source:
            return self.save_stream(source, key)

    @contextmanager
    def materialize(self, reference: str) -> Iterator[str]:
        try:
            object_key = validate_storage_key(reference)
        except ValueError as error:
            raise StorageObjectNotFound(
                "The uploaded video is no longer available. Please upload the video again."
            ) from error
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=object_key)
        except ClientError as error:
            if _is_not_found(error):
                raise StorageObjectNotFound(
                    "The uploaded video is no longer available. Please upload the video again."
                ) from error
            logger.error(
                "R2 video lookup failed error_type=%s",
                type(error).__name__,
            )
            raise StorageError("Unable to access video storage.") from error
        except Exception as error:
            logger.error(
                "R2 video lookup failed error_type=%s",
                type(error).__name__,
            )
            raise StorageError("Unable to access video storage.") from error

        suffix = Path(object_key).suffix
        with tempfile.TemporaryDirectory(prefix="videomind-r2-") as directory:
            local_path = Path(directory) / f"source{suffix}"
            try:
                self._client.download_file(
                    self.bucket_name,
                    object_key,
                    str(local_path),
                    Config=self._transfer_config,
                )
            except ClientError as error:
                if _is_not_found(error):
                    raise StorageObjectNotFound(
                        "The uploaded video is no longer available. Please upload the video again."
                    ) from error
                logger.error(
                    "R2 video download failed error_type=%s",
                    type(error).__name__,
                )
                raise StorageError("Unable to access video storage.") from error
            except Exception as error:
                logger.error(
                    "R2 video download failed error_type=%s",
                    type(error).__name__,
                )
                raise StorageError("Unable to access video storage.") from error
            yield str(local_path)

    def exists(self, reference: str) -> bool:
        try:
            object_key = validate_storage_key(reference)
        except ValueError:
            return False
        try:
            self._client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as error:
            if _is_not_found(error):
                return False
            logger.error(
                "R2 video existence check failed error_type=%s",
                type(error).__name__,
            )
            raise StorageError("Unable to access video storage.") from error
        except Exception as error:
            logger.error(
                "R2 video existence check failed error_type=%s",
                type(error).__name__,
            )
            raise StorageError("Unable to access video storage.") from error

    def delete(self, reference: str) -> None:
        try:
            object_key = validate_storage_key(reference)
        except ValueError as error:
            raise StorageError("Invalid stored video reference.") from error
        try:
            self._client.delete_object(Bucket=self.bucket_name, Key=object_key)
        except Exception as error:
            logger.error(
                "R2 video deletion failed error_type=%s",
                type(error).__name__,
            )
            raise StorageError("Unable to remove stored video.") from error

    @contextmanager
    def frame_workspace(self, video_id: int) -> Iterator[str]:
        with self._local.frame_workspace(video_id) as frames_root:
            yield frames_root