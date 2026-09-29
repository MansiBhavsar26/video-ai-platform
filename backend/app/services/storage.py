"""Safe local filesystem storage for uploaded videos and analysis frames."""

from __future__ import annotations

import logging
import shutil
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator

from .. import config


logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Safe, user-facing local storage failure."""


class StorageObjectNotFound(StorageError):
    """The stored source video is no longer available."""


def validate_storage_key(key: str) -> str:
    """Validate a generated relative path before using it under UPLOAD_DIR."""
    if not isinstance(key, str) or not key or "\\" in key:
        raise ValueError("Invalid storage path.")
    path = PurePosixPath(key)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in key.split("/")):
        raise ValueError("Invalid storage path.")
    if path.drive or ":" in path.parts[0]:
        raise ValueError("Invalid storage path.")
    return path.as_posix()


def make_video_storage_key(token: str, extension: str) -> str:
    """Build a path from generated values, never from the submitted filename."""
    safe_extension = extension.lower()
    if safe_extension not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise ValueError("Invalid video extension.")
    return validate_storage_key(f"videos/{token}/source{safe_extension}")


class LocalStorageBackend:
    """Store source videos under UPLOAD_DIR and frames under FRAMES_DIR."""

    def __init__(self, upload_dir: str | Path, frames_dir: str | Path):
        self.upload_dir = Path(upload_dir).expanduser().resolve()
        self.frames_dir = Path(frames_dir).expanduser().resolve()
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        safe_key = validate_storage_key(key)
        root = self.upload_dir.resolve()
        target = root.joinpath(*PurePosixPath(safe_key).parts).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Invalid storage path.")
        return target

    def save_stream(self, source: BinaryIO, key: str) -> str:
        target = None
        try:
            target = self._path_for_key(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            source.seek(0)
            with target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            return str(target)
        except Exception as error:
            if target is not None:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Local storage write cleanup failed")
            logger.exception("Local storage write failed")
            raise StorageError("Unable to store video.") from error

    def save_file(self, source_path: str | Path, key: str) -> str:
        with open(source_path, "rb") as source:
            return self.save_stream(source, key)

    @contextmanager
    def materialize(self, reference: str) -> Iterator[str]:
        path = Path(reference).expanduser().resolve()
        if not path.is_relative_to(self.upload_dir.resolve()):
            raise StorageError("Invalid stored video reference.")
        if not path.is_file():
            raise StorageObjectNotFound(
                "The uploaded video is no longer available. Please upload the video again."
            )
        yield str(path)

    def exists(self, reference: str) -> bool:
        try:
            with self.materialize(reference):
                return True
        except StorageObjectNotFound:
            return False

    def delete(self, reference: str) -> None:
        path = Path(reference).expanduser().resolve()
        if not path.is_relative_to(self.upload_dir.resolve()):
            raise StorageError("Invalid stored video reference.")
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            logger.exception("Local storage delete failed")
            raise StorageError("Unable to remove stored video.") from error

    @contextmanager
    def frame_workspace(self, video_id: int) -> Iterator[str]:
        workspace = self.frames_dir / str(int(video_id))
        workspace.mkdir(parents=True, exist_ok=True)
        yield str(self.frames_dir)


_local_storage: LocalStorageBackend | None = None


def get_local_storage() -> LocalStorageBackend:
    """Return the configured local filesystem storage instance."""
    global _local_storage
    if _local_storage is None:
        _local_storage = LocalStorageBackend(config.UPLOAD_DIR, config.FRAMES_DIR)
    return _local_storage
