from io import BytesIO
from pathlib import Path

import pytest

from app.services.storage import (
    LocalStorageBackend,
    StorageError,
    StorageObjectNotFound,
    make_video_storage_key,
    validate_storage_key,
)


def test_local_storage_save_read_exists_delete_and_frame_workspace(tmp_path):
    backend = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    key = make_video_storage_key("abc123", ".mp4")
    reference = backend.save_stream(BytesIO(b"sample-video"), key)

    assert Path(reference).read_bytes() == b"sample-video"
    assert backend.exists(reference)
    with backend.materialize(reference) as local_path:
        assert Path(local_path).read_bytes() == b"sample-video"
    with backend.frame_workspace(5) as frames_root:
        assert Path(frames_root) == tmp_path / "frames"
        assert (Path(frames_root) / "5").is_dir()

    backend.delete(reference)
    assert not backend.exists(reference)


@pytest.mark.parametrize(
    "key",
    [
        "../outside.mp4",
        "videos/../../outside.mp4",
        r"C:\\outside.mp4",
        "/absolute/video.mp4",
        "videos//empty.mp4",
    ],
)
def test_storage_rejects_traversal_and_absolute_keys(key):
    with pytest.raises(ValueError):
        validate_storage_key(key)


def test_video_storage_key_uses_generated_safe_relative_components():
    key = make_video_storage_key("a1b2c3", ".MOV")

    assert key == "videos/a1b2c3/source.mov"
    assert not key.startswith("/")
    assert ".." not in key


def test_local_storage_delete_refuses_paths_outside_upload_root(tmp_path):
    backend = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("preserve", encoding="utf-8")

    with pytest.raises(StorageError, match="Invalid stored video reference"):
        backend.delete(str(unrelated))

    assert unrelated.read_text(encoding="utf-8") == "preserve"


def test_local_storage_materialize_reports_missing_media_safely(tmp_path):
    backend = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    missing = backend._path_for_key("videos/gone/source.mp4")

    with pytest.raises(StorageObjectNotFound) as error:
        with backend.materialize(str(missing)):
            pass

    assert str(error.value) == (
        "The uploaded video is no longer available. Please upload the video again."
    )
