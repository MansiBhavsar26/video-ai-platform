import gc
from pathlib import Path

from ultralytics import YOLO

from ..config import YOLO_MAX_DETECTIONS, YOLO_MODEL_PATH


model = None


def _get_model():
    global model

    if model is None:
        model_path = Path(YOLO_MODEL_PATH)
        if not model_path.is_file():
            raise RuntimeError(
                "YOLO model file is not available for video analysis."
            )
        model = YOLO(str(model_path))

    return model


def release_model():
    """Drop the cached YOLO model after one local analysis job."""
    global model

    detector = model
    model = None
    was_loaded = detector is not None
    del detector
    if was_loaded:
        gc.collect()


def detect_objects(image_path: str):
    detector = _get_model()

    detections = []
    results = detector.predict(
        image_path,
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
