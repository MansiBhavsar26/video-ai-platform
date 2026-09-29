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
        "get_local_storage",
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
        "get_local_storage",
        lambda: LocalStorageBackend(tmp_path, tmp_path / "frames"),
    )
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 1024)
    db = FakeDB()

    with pytest.raises(HTTPException, match=message):
        videos.upload_video(_upload(filename, content, content_type), db)

    assert db.added == []
    assert list((tmp_path / "videos").rglob("*")) == []


def test_upload_enforces_configured_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        videos,
        "get_local_storage",
        lambda: LocalStorageBackend(tmp_path, tmp_path / "frames"),
    )
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 4)

    with pytest.raises(HTTPException) as error:
        videos.upload_video(_upload("tutorial.mp4", b"12345"), FakeDB())

    assert error.value.status_code == 413
    assert list((tmp_path / "videos").rglob("*")) == []


def test_analyze_missing_local_video_returns_safe_reupload_message(tmp_path, monkeypatch):
    storage = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    monkeypatch.setattr(videos, "get_local_storage", lambda: storage)
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
