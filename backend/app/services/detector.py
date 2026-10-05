import gc
import logging
from pathlib import Path
from threading import Lock

from ..config import YOLO_MAX_DETECTIONS, YOLO_MODEL_PATH


model = None
YOLO = None
check_file = None
logger = logging.getLogger(__name__)
_model_lock = Lock()
_inference_lock = Lock()
YOLO_INFERENCE_SIZE = 416
_YOLO11N_URL = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"


def _ensure_model_file(model_path: Path) -> Path:
    if model_path.is_file():
        return model_path

    # Only auto-fetch the known lightweight model into the configured local cache.
    if model_path.name != "yolo11n.pt":
        raise RuntimeError("Configured YOLO model file is unavailable.")

    try:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        file_checker = check_file
        if file_checker is None:
            from ultralytics.utils.checks import check_file as file_checker

        downloaded = Path(
            file_checker(_YOLO11N_URL, download_dir=str(model_path.parent))
        )
        if downloaded.name != model_path.name or not downloaded.is_file():
            raise RuntimeError("YOLO model download did not produce the expected file.")
        return downloaded
    except Exception as error:
        logger.warning("YOLO11n model could not be obtained for this instance.")
        raise RuntimeError("YOLO model is unavailable for video analysis.") from error


def _get_model():
    global model

    if model is None:
        with _model_lock:
            if model is None:
                model_path = _ensure_model_file(Path(YOLO_MODEL_PATH))
                yolo_class = YOLO
                if yolo_class is None:
                    from ultralytics import YOLO as yolo_class
                model = yolo_class(str(model_path))

    return model


def release_model():
    """Drop the cached YOLO model after one local analysis job."""
    global model

    with _inference_lock:
        with _model_lock:
            detector = model
            model = None
        was_loaded = detector is not None
        del detector
        if was_loaded:
            gc.collect()


def detect_objects(image_path: str):
    with _inference_lock:
        detector = _get_model()

        detections = []
        results = detector.predict(
            image_path,
            imgsz=YOLO_INFERENCE_SIZE,
            batch=1,
            device="cpu",
            stream=False,
            verbose=False,
            max_det=YOLO_MAX_DETECTIONS,
        )

        try:
            for result in results:
                for box in result.boxes:
                    if len(detections) >= YOLO_MAX_DETECTIONS:
                        break
                    class_id = int(box.cls[0])
                    detections.append(
                        {
                            "label": detector.names[class_id],
                            "confidence": float(box.conf[0]),
                            "x1": float(box.xyxy[0][0]),
                            "y1": float(box.xyxy[0][1]),
                            "x2": float(box.xyxy[0][2]),
                            "y2": float(box.xyxy[0][3]),
                        }
                    )
                if len(detections) >= YOLO_MAX_DETECTIONS:
                    break
        finally:
            del results

    return detections
