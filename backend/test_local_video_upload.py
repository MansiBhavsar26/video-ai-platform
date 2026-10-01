from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from starlette.datastructures import UploadFile

from app.routes import videos
from app.services.storage import LocalStorageBackend


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    def commit(self):
        pass

    def refresh(self, value):
        value.id = 17


class FakeVideoQuery:
    def __init__(self, video):
        self.video = video

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.video


class FakeVideoDB:
    def __init__(self, video):
        self.video = video

    def query(self, model):
        return FakeVideoQuery(self.video)


def _upload(filename, content, content_type="video/mp4"):
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers={"content-type": content_type},
    )


def test_upload_creates_upload_record_without_exposing_path(tmp_path, monkeypatch):
    monkeypatch.setattr(
        videos,
        "get_video_storage",
        lambda: LocalStorageBackend(tmp_path, tmp_path / "frames"),
    )
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 1024)
    monkeypatch.setattr(videos, "get_video_info", lambda path: {"duration": 12, "fps": 30})
    db = FakeDB()

    result = videos.upload_video(_upload("..\\outside.mp4", b"video"), db)

    assert result["id"] == 17
    assert result["source_type"] == "upload"
    assert "filepath" not in result
    assert len(list((tmp_path / "videos").rglob("source.mp4"))) == 1
    record = db.added[0]
    assert record.source_type == "upload"
    assert Path(record.filepath).is_relative_to(tmp_path / "videos")


def test_upload_persists_object_key_in_video_record(tmp_path, monkeypatch):
    class KeyStorage:
        def __init__(self):
            self.saved_key = None
            self.content = b""

        def save_stream(self, source, key):
            self.saved_key = key
            chunks = []
            while chunk := source.read(3):
                chunks.append(chunk)
            self.content = b"".join(chunks)
            return key

        def delete(self, reference):
            pass

    storage = KeyStorage()
    monkeypatch.setattr(videos, "get_video_storage", lambda: storage)
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 1024)
    monkeypatch.setattr(videos, "get_video_info", lambda path: {"duration": 12, "fps": 30})
    db = FakeDB()

    result = videos.upload_video(_upload("tutorial.mp4", b"streamed-video"), db)

    record = db.added[0]
    assert result["id"] == 17
    assert record.filepath == storage.saved_key
    assert record.filepath.startswith("videos/")
    assert not Path(record.filepath).is_absolute()
    assert storage.content == b"streamed-video"


@pytest.mark.parametrize(
    "filename,content,content_type,message",
    [
        ("tutorial.avi", b"video", "video/x-msvideo", "Unsupported video format"),
        ("tutorial.mp4", b"", "video/mp4", "empty"),
        ("tutorial.mp4", b"video", "text/plain", "content type"),
    ],
)
def test_upload_rejects_invalid_files(tmp_path, monkeypatch, filename, content, content_type, message):
    monkeypatch.setattr(
        videos,
        "get_video_storage",
        lambda: LocalStorageBackend(tmp_path, tmp_path / "frames"),
    )
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 1024)
    db = FakeDB()

    with pytest.raises(HTTPException, match=message):
        videos.upload_video(_upload(filename, content, content_type), db)

    assert db.added == []
    assert list((tmp_path / "videos").rglob("*")) == []


def test_upload_enforces_configured_size_limit(tmp_path, monkeypatch):
    storage_initializations = []
    monkeypatch.setattr(
        videos,
        "get_video_storage",
        lambda: storage_initializations.append(True),
    )
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 4)

    with pytest.raises(HTTPException) as error:
        videos.upload_video(_upload("tutorial.mp4", b"12345"), FakeDB())

    assert error.value.status_code == 413
    assert "4 bytes" in error.value.detail
    assert storage_initializations == []
    assert list((tmp_path / "videos").rglob("*")) == []


def test_upload_rejects_over_duration_before_persistent_storage(tmp_path, monkeypatch):
    storage_initializations = []
    temporary_paths = []
    monkeypatch.setattr(
        videos,
        "get_video_storage",
        lambda: storage_initializations.append(True),
    )
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 1024)
    monkeypatch.setattr(videos, "VIDEO_ANALYSIS_MAX_DURATION_SECONDS", 30)

    def get_video_info(path):
        temporary_paths.append(Path(path))
        return {"duration": 31, "fps": 30}

    monkeypatch.setattr(videos, "get_video_info", get_video_info)
    db = FakeDB()

    with pytest.raises(HTTPException) as error:
        videos.upload_video(_upload("tutorial.mp4", b"video"), db)

    assert error.value.status_code == 422
    assert "up to 1 minutes" in error.value.detail
    assert storage_initializations == []
    assert db.added == []
    assert len(temporary_paths) == 1
    assert not temporary_paths[0].exists()


@pytest.mark.parametrize("duration", [0, None, float("nan"), float("inf"), "invalid"])
def test_upload_rejects_unknown_or_invalid_duration(
    tmp_path,
    monkeypatch,
    duration,
):
    storage_initializations = []
    monkeypatch.setattr(
        videos,
        "get_video_storage",
        lambda: storage_initializations.append(True),
    )
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 1024)
    monkeypatch.setattr(
        videos,
        "get_video_info",
        lambda path: {"duration": duration, "fps": 30},
    )

    with pytest.raises(HTTPException) as error:
        videos.upload_video(_upload("tutorial.mp4", b"video"), FakeDB())

    assert error.value.status_code == 422
    assert "duration could not be determined" in error.value.detail
    assert "source" not in error.value.detail.lower()
    assert storage_initializations == []


def test_analyze_rejects_unknown_duration_before_scheduling(tmp_path, monkeypatch):
    storage = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    filepath = storage.save_stream(
        BytesIO(b"video"),
        "videos/unknown-duration/source.mp4",
    )
    monkeypatch.setattr(videos, "get_video_storage", lambda: storage)
    video = SimpleNamespace(
        id=25,
        status="uploaded",
        filepath=filepath,
        duration=0,
    )
    tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as error:
        videos.analyze_uploaded_video(25, tasks, FakeVideoDB(video))

    assert error.value.status_code == 422
    assert "duration could not be determined" in error.value.detail
    assert not tasks.tasks
    assert video.status == "uploaded"


def test_analyze_missing_local_video_returns_safe_reupload_message(tmp_path, monkeypatch):
    storage = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    monkeypatch.setattr(videos, "get_video_storage", lambda: storage)
    video = SimpleNamespace(
        id=23,
        status="uploaded",
        filepath=str(tmp_path / "uploads" / "videos" / "gone" / "source.mp4"),
    )

    with pytest.raises(HTTPException) as error:
        videos.analyze_uploaded_video(
            23,
            BackgroundTasks(),
            FakeVideoDB(video),
        )

    assert error.value.status_code == 410
    assert error.value.detail == (
        "The uploaded video is no longer available. Please upload the video again."
    )
    assert video.status == "uploaded"


def test_analyze_reports_storage_configuration_failure_safely(monkeypatch):
    video = SimpleNamespace(
        id=26,
        status="uploaded",
        filepath="videos/test/source.mp4",
        duration=12,
    )
    tasks = BackgroundTasks()

    def unavailable_storage():
        raise videos.StorageError("R2 configuration is incomplete")

    monkeypatch.setattr(videos, "get_video_storage", unavailable_storage)

    with pytest.raises(HTTPException) as error:
        videos.analyze_uploaded_video(26, tasks, FakeVideoDB(video))

    assert error.value.status_code == 503
    assert error.value.detail == "Video storage is unavailable."
    assert not tasks.tasks


def test_failed_video_status_reports_missing_source_without_path(tmp_path, monkeypatch):
    storage = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    monkeypatch.setattr(videos, "get_video_storage", lambda: storage)
    video = SimpleNamespace(
        id=24,
        status="failed",
        filepath=str(tmp_path / "uploads" / "videos" / "private-path" / "source.mp4"),
        duration=12,
    )

    result = videos.get_video_status(24, FakeVideoDB(video))

    assert result["message"] == (
        "The uploaded video is no longer available. Please upload the video again."
    )
    assert str(tmp_path) not in result["message"]
