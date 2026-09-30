import os

from app import config
from app.services import detector, transcription


def test_transcription_release_drops_cached_model(monkeypatch):
    monkeypatch.setattr(transcription, "_model", object())

    transcription.release_model()

    assert transcription._model is None


def test_detector_release_drops_cached_model(monkeypatch):
    monkeypatch.setattr(detector, "model", object())

    detector.release_model()

    assert detector.model is None


def test_detector_loads_lazily_once_per_analysis(tmp_path, monkeypatch):
    weights = tmp_path / "weights.pt"
    weights.write_bytes(b"test weights placeholder")
    loads = []

    class FakeYOLO:
        def __init__(self, path):
            loads.append(path)

    monkeypatch.setattr(detector, "YOLO", FakeYOLO)
    monkeypatch.setattr(detector, "YOLO_MODEL_PATH", str(weights))
    monkeypatch.setattr(detector, "model", None)

    assert not loads
    detector._get_model()
    detector._get_model()

    assert loads == [str(weights)]


def test_yolo_inference_caps_detections_per_frame(monkeypatch):
    options = {}

    class FakeBox:
        cls = [0]
        conf = [0.9]
        xyxy = [[0, 0, 1, 1]]

    class FakeResult:
        boxes = [FakeBox() for _ in range(config.YOLO_MAX_DETECTIONS + 5)]

    class FakeModel:
        names = {0: "object"}

        def predict(self, image_path, **kwargs):
            options.update(kwargs)
            return [FakeResult()]

    monkeypatch.setattr(detector, "model", FakeModel())

    detections = detector.detect_objects("synthetic-frame.jpg")
    assert len(detections) == config.YOLO_MAX_DETECTIONS
    assert options["max_det"] == config.YOLO_MAX_DETECTIONS


def test_render_mvp_uses_tiny_whisper_model():
    assert transcription.MODEL_SIZE == "tiny"


def test_default_video_frame_limit_is_60():
    assert config.VIDEO_ANALYSIS_MAX_FRAMES == int(
        os.getenv("VIDEO_ANALYSIS_MAX_FRAMES", "60")
    )
