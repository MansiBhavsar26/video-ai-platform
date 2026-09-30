from pathlib import Path

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import (
    TranscriptSegment,
    TutorialStep,
    Video,
)
from app.routes import videos
from app.routes import youtube as youtube_route


client = TestClient(app)
YOUTUBE_URL = "https://www.youtube.com/watch?v=S66rHpyU-Eg"
VIDEO_ID = "S66rHpyU-Eg"


def remove_video(video_id: str):
    db = SessionLocal()
    try:
        video = db.query(Video).filter(
            Video.youtube_video_id == video_id
        ).first()
        if video:
            db.delete(video)
            db.commit()
    finally:
        db.close()


def test_youtube_url_uses_transcript_pipeline_without_download(
    monkeypatch,
):
    remove_video(VIDEO_ID)
    transcript = {
        "segments": [
            {
                "start_time": 0,
                "end_time": 2,
                "text": "can do NPM install that save react router dom",
            },
        ],
        "language": "English",
        "language_code": "en",
        "is_generated": False,
    }

    def fail_download(url):
        raise AssertionError("YouTube URL must not use video acquisition")

    monkeypatch.setattr(videos, "acquire_video_from_url", fail_download)
    monkeypatch.setattr(
        youtube_route,
        "fetch_youtube_transcript",
        lambda video_id: transcript,
    )

    response = client.post("/videos/url", params={"url": YOUTUBE_URL})

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_type"] == "youtube"
    assert payload["youtube_video_id"] == VIDEO_ID
    assert payload["status"] == "completed"

    db = SessionLocal()
    try:
        video = db.query(Video).filter(
            Video.youtube_video_id == VIDEO_ID
        ).first()
        assert video is not None
        assert video.youtube_url == YOUTUBE_URL
        assert video.status == "completed"
        assert db.query(TranscriptSegment).filter(
            TranscriptSegment.video_id == video.id
        ).count() == 1
        assert db.query(TutorialStep).filter(
            TutorialStep.video_id == video.id
        ).count() == 1
    finally:
        db.close()
        remove_video(VIDEO_ID)


def test_youtube_transcript_failure_is_safe(monkeypatch):
    remove_video(VIDEO_ID)

    monkeypatch.setattr(
        youtube_route,
        "fetch_youtube_transcript",
        lambda video_id: (_ for _ in ()).throw(
            RuntimeError("private transcript provider detail")
        ),
    )

    response = client.post("/videos/url", params={"url": YOUTUBE_URL})

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Unable to analyze this YouTube tutorial."
    )
    assert "private transcript provider detail" not in response.text

    db = SessionLocal()
    try:
        video = db.query(Video).filter(
            Video.youtube_video_id == VIDEO_ID
        ).first()
        assert video is not None
        assert video.status == "failed"
    finally:
        db.close()
        remove_video(VIDEO_ID)


def test_existing_completed_youtube_video_is_idempotent(monkeypatch):
    remove_video(VIDEO_ID)
    db = SessionLocal()
    video = Video(
        filename=f"youtube_{VIDEO_ID}",
        youtube_url=YOUTUBE_URL,
        youtube_video_id=VIDEO_ID,
        source_type="youtube",
        status="completed",
    )
    db.add(video)
    db.commit()
    db.close()

    def fail_transcript(video_id):
        raise AssertionError("Completed videos should not be reprocessed")

    monkeypatch.setattr(
        youtube_route,
        "fetch_youtube_transcript",
        fail_transcript,
    )

    response = client.post("/videos/url", params={"url": YOUTUBE_URL})

    assert response.status_code == 200
    assert response.json()["message"] == "This YouTube video already exists."
    remove_video(VIDEO_ID)


def test_non_youtube_url_keeps_existing_acquisition_flow(monkeypatch, tmp_path):
    from app.services.storage import LocalStorageBackend

    filepath = Path(tmp_path) / "sample.mp4"
    filepath.write_bytes(b"video")
    calls = []
    storage = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")

    def acquire(url, *, max_bytes):
        calls.append(url)
        assert max_bytes == videos.UPLOAD_MAX_BYTES
        return {
            "filepath": str(filepath),
            "title": "sample",
            "source_type": "direct",
        }

    monkeypatch.setattr(videos, "acquire_video_from_url", acquire)
    monkeypatch.setattr(videos, "get_local_storage", lambda: storage)
    monkeypatch.setattr(
        videos,
        "get_video_info",
        lambda path: {"duration": 1, "fps": 24},
    )

    response = client.post(
        "/videos/url",
        params={"url": "https://example.com/sample.mp4"},
    )

    assert response.status_code == 200
    assert calls == ["https://example.com/sample.mp4"]
    assert "filepath" not in response.json()
    video_id = response.json()["id"]

    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        assert video is not None
        stored_path = Path(video.filepath)
        db.delete(video)
        db.commit()
    finally:
        db.close()
    storage.delete(str(stored_path))
