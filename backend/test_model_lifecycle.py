import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from time import sleep

import pytest

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


def test_missing_default_yolo_weights_downloads_once_to_configured_cache(
    tmp_path, monkeypatch
):
    model_path = tmp_path / "cache" / "yolo11n.pt"
    downloads = []
    loads = []

    def fake_check_file(url, download_dir):
        downloads.append((url, download_dir))
        downloaded = tmp_path / "cache" / "yolo11n.pt"
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        downloaded.write_bytes(b"test weights")
        return str(downloaded)

    class FakeYOLO:
        def __init__(self, path):
            loads.append(path)

    monkeypatch.setattr(detector, "YOLO", FakeYOLO)
    monkeypatch.setattr(detector, "check_file", fake_check_file)
    monkeypatch.setattr(detector, "YOLO_MODEL_PATH", str(model_path))
    monkeypatch.setattr(detector, "model", None)

    detector._get_model()
    detector._get_model()

    assert len(downloads) == 1
    assert downloads[0][0].endswith("/yolo11n.pt")
    assert Path(downloads[0][1]) == model_path.parent
    assert loads == [str(model_path)]


def test_missing_custom_yolo_model_does_not_download_other_weights(
    tmp_path, monkeypatch
):
    downloads = []
    monkeypatch.setattr(detector, "YOLO_MODEL_PATH", str(tmp_path / "custom.pt"))
    monkeypatch.setattr(detector, "check_file", lambda *args, **kwargs: downloads.append(True))

    with pytest.raises(RuntimeError, match="unavailable"):
        detector._ensure_model_file(tmp_path / "custom.pt")

    assert not downloads


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
    assert options["imgsz"] == 416
    assert options["batch"] == 1
    assert options["device"] == "cpu"
    assert options["max_det"] == config.YOLO_MAX_DETECTIONS


def test_yolo_inference_is_serialized_across_video_jobs(monkeypatch):
    state_lock = Lock()
    active = 0
    maximum_active = 0

    class FakeModel:
        names = {}

        def predict(self, image_path, **kwargs):
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            sleep(0.02)
            with state_lock:
                active -= 1
            return []

    monkeypatch.setattr(detector, "model", FakeModel())
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(detector.detect_objects, ["frame.jpg"] * 8))

    assert maximum_active == 1


def test_render_mvp_uses_tiny_whisper_model():
    assert transcription.MODEL_SIZE == "tiny"


def test_default_video_frame_limit_is_30():
    assert config.VIDEO_ANALYSIS_MAX_FRAMES == int(
        os.getenv("VIDEO_ANALYSIS_MAX_FRAMES", "30")
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("false", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("no", False),
    ],
)
def test_object_detection_boolean_parser(value, expected):
    assert config._parse_boolean(value, default=True) is expected


def test_object_detection_boolean_parser_uses_local_default():
    assert config._parse_boolean(None, default=True) is True


def test_object_detection_boolean_parser_rejects_unknown_values():
    with pytest.raises(ValueError, match="ENABLE_OBJECT_DETECTION"):
        config._parse_boolean("sometimes", default=True)


def test_disabled_application_import_does_not_load_torch_or_ultralytics(tmp_path):
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": f"sqlite:///{(tmp_path / 'disabled.sqlite').as_posix()}",
            "ENABLE_OBJECT_DETECTION": "false",
            "UPLOAD_DIR": str(tmp_path / "uploads"),
            "FRAMES_DIR": str(tmp_path / "frames"),
            "SUPADATA_API_KEY": "",
        }
    )
    code = (
        "import sys; import app.main; "
        "assert 'torch' not in sys.modules; "
        "assert 'ultralytics' not in sys.modules"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
