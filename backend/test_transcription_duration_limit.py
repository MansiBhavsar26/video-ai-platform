import pytest

from app.services import transcription, video_processor


@pytest.mark.parametrize("duration", [0, None, float("nan"), float("inf"), "invalid"])
def test_video_duration_validation_fails_closed(duration):
    with pytest.raises(video_processor.VideoDurationError, match="duration could not be determined"):
        video_processor.validate_video_duration(duration, max_duration=1800)


def test_video_duration_validation_rejects_over_limit():
    with pytest.raises(video_processor.VideoDurationError, match="up to 30 minutes"):
        video_processor.validate_video_duration(1801, max_duration=1800)


@pytest.mark.parametrize("fps,frame_count", [
    (0, 300),
    (float("nan"), 300),
    (30, 0),
    (30, float("inf")),
])
def test_video_probe_rejects_invalid_metadata_and_releases_capture(
    monkeypatch,
    fps,
    frame_count,
):
    class FakeCapture:
        released = False

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == video_processor.cv2.CAP_PROP_FPS:
                return fps
            return frame_count

        def release(self):
            self.released = True

    capture = FakeCapture()
    monkeypatch.setattr(video_processor.cv2, "VideoCapture", lambda path: capture)

    with pytest.raises(video_processor.VideoDurationError):
        video_processor.get_video_info("unused.mp4")

    assert capture.released


def test_video_probe_reports_unopenable_video_as_unknown_duration(monkeypatch):
    class ClosedCapture:
        released = False

        def isOpened(self):
            return False

        def release(self):
            self.released = True

    capture = ClosedCapture()
    monkeypatch.setattr(video_processor.cv2, "VideoCapture", lambda path: capture)

    with pytest.raises(
        video_processor.VideoDurationError,
        match="duration could not be determined",
    ):
        video_processor.get_video_info("unused.mp4")

    assert capture.released


@pytest.mark.parametrize("max_duration", [0, None, float("nan"), float("inf"), "invalid"])
def test_transcription_rejects_invalid_max_duration_before_loading_model(
    monkeypatch,
    max_duration,
):
    monkeypatch.setattr(
        transcription,
        "get_model",
        lambda: pytest.fail("invalid duration reached Whisper"),
    )

    with pytest.raises(ValueError, match="valid maximum transcription duration"):
        transcription.transcribe_video("unused.mp4", max_duration=max_duration)


def test_transcription_fails_closed_for_unknown_video_duration(monkeypatch):
    monkeypatch.setattr(
        transcription,
        "get_video_info",
        lambda path: {"duration": float("nan")},
    )
    monkeypatch.setattr(
        transcription,
        "get_model",
        lambda: pytest.fail("invalid duration reached Whisper"),
    )

    with pytest.raises(video_processor.VideoDurationError):
        transcription.transcribe_video("video.mp4", max_duration=1800)
