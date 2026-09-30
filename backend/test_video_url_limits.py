from pathlib import Path

import pytest
import yt_dlp

from app.routes import videos
from app.services import video_url


class StreamResponse:
    def __init__(self, chunks, content_type="video/mp4"):
        self.chunks = chunks
        self.headers = {"content-type": content_type}
        self.closed = False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        assert chunk_size == 1024 * 1024
        yield from self.chunks

    def close(self):
        self.closed = True


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, record):
        self.added.append(record)

    def commit(self):
        pass

    def refresh(self, record):
        record.id = 91


class FakeStorage:
    def __init__(self):
        self.saved = []

    def save_file(self, path, key):
        self.saved.append((path, key))
        return key

    def delete(self, reference):
        pass


def test_direct_url_download_within_limit_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(video_url.tempfile, "tempdir", str(tmp_path))
    response = StreamResponse([b"1234", b"5678"])
    monkeypatch.setattr(video_url.requests, "get", lambda *args, **kwargs: response)

    result = video_url.acquire_video_from_url(
        "https://example.test/sample.mp4",
        max_bytes=8,
    )

    filepath = Path(result["filepath"])
    assert filepath.read_bytes() == b"12345678"
    assert response.closed
    filepath.unlink()


def test_direct_url_download_aborts_and_deletes_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(video_url.tempfile, "tempdir", str(tmp_path))
    response = StreamResponse([b"1234", b"56789"])
    monkeypatch.setattr(video_url.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(video_url.VideoTooLargeError):
        video_url.acquire_video_from_url(
            "https://example.test/sample.mp4",
            max_bytes=8,
        )

    assert response.closed
    assert list(tmp_path.iterdir()) == []


def test_oversized_direct_url_never_reaches_persistent_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(video_url.tempfile, "tempdir", str(tmp_path))
    response = StreamResponse([b"1234", b"56789"])
    monkeypatch.setattr(video_url.requests, "get", lambda *args, **kwargs: response)
    storage = FakeStorage()
    monkeypatch.setattr(videos, "get_local_storage", lambda: storage)
    monkeypatch.setattr(videos, "UPLOAD_MAX_BYTES", 8)
    db = FakeDB()

    with pytest.raises(videos.HTTPException) as error:
        videos.add_video_from_url(
            "https://example.test/sample.mp4",
            db,
        )

    assert error.value.status_code == 413
    assert "8 bytes" in error.value.detail
    assert storage.saved == []
    assert db.added == []
    assert list(tmp_path.iterdir()) == []


def test_over_duration_url_media_is_rejected_before_persistent_storage(
    tmp_path,
    monkeypatch,
):
    filepath = tmp_path / "source.mp4"
    filepath.write_bytes(b"video")
    storage = FakeStorage()
    monkeypatch.setattr(videos, "get_local_storage", lambda: storage)
    monkeypatch.setattr(videos, "VIDEO_ANALYSIS_MAX_DURATION_SECONDS", 30)
    monkeypatch.setattr(
        videos,
        "acquire_video_from_url",
        lambda url, *, max_bytes: {
            "filepath": str(filepath),
            "source_type": "direct",
        },
    )
    monkeypatch.setattr(
        videos,
        "get_video_info",
        lambda path: {"duration": 31, "fps": 30},
    )
    db = FakeDB()

    with pytest.raises(videos.HTTPException) as error:
        videos.add_video_from_url(
            "https://example.test/sample.mp4",
            db,
        )

    assert error.value.status_code == 422
    assert "up to 1 minutes" in error.value.detail
    assert storage.saved == []
    assert db.added == []
    assert not filepath.exists()


@pytest.mark.parametrize("exceed_in_hook", [False, True])
def test_ytdlp_uses_early_and_final_size_guards_and_cleans_partial(
    tmp_path,
    monkeypatch,
    exceed_in_hook,
):
    download_directory = tmp_path / "download"

    def make_download_directory(**kwargs):
        download_directory.mkdir()
        return str(download_directory)

    monkeypatch.setattr(video_url.tempfile, "mkdtemp", make_download_directory)
    observed = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            observed.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            output = download_directory / "sample.mp4"
            output.write_bytes(b"partial")
            if exceed_in_hook:
                observed["progress_hooks"][0](
                    {"filename": str(output), "downloaded_bytes": 9}
                )
            else:
                output.write_bytes(b"123456789")
            return {"id": "sample", "ext": "mp4"}

    monkeypatch.setattr(video_url.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    with pytest.raises(video_url.VideoTooLargeError):
        video_url.acquire_video_from_url(
            "https://example.test/watch?id=sample",
            max_bytes=8,
        )

    assert observed["max_filesize"] == 8
    assert len(observed["progress_hooks"]) == 1
    assert not download_directory.exists()
    if not exceed_in_hook:
        with pytest.raises(
            yt_dlp.utils.DownloadError,
            match="VIDEOMIND_UPLOAD_SIZE_LIMIT_EXCEEDED",
        ):
            observed["progress_hooks"][0](
                {"filename": "sample.mp4", "downloaded_bytes": 9}
            )


def test_youtube_acquisition_never_invokes_ytdlp(monkeypatch):
    def fail_download(*args, **kwargs):
        raise AssertionError("YouTube video download must not be attempted")

    monkeypatch.setattr(video_url.yt_dlp, "YoutubeDL", fail_download)

    with pytest.raises(ValueError, match="supported YouTube URL"):
        video_url.acquire_video_from_url(
            "https://www.youtube.com/live/unsupported-id",
            max_bytes=1024,
        )
