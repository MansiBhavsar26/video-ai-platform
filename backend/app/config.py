import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL is not configured."
    )


def _parse_boolean(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("ENABLE_OBJECT_DETECTION must be a boolean value.")


ENABLE_OBJECT_DETECTION = _parse_boolean(
    os.getenv("ENABLE_OBJECT_DETECTION"),
    default=True,
)


TESSERACT_PATH = os.getenv(
    "TESSERACT_PATH",
    "",
)


SUPADATA_API_KEY = os.getenv(
    "SUPADATA_API_KEY",
)


SUPADATA_TIMEOUT_SECONDS = float(
    os.getenv(
        "SUPADATA_TIMEOUT_SECONDS",
        "30",
    )
)


BASE_DIR = Path(__file__).resolve().parents[1]


def _configured_directory(environment_variable: str, default: Path) -> str:
    """Return an absolute, platform-native directory from configuration."""
    configured_path = Path(os.getenv(environment_variable, str(default))).expanduser()
    return str(configured_path.resolve())


PORT = int(os.getenv("PORT", "8000"))


UPLOAD_DIR = _configured_directory("UPLOAD_DIR", BASE_DIR / "uploads")

UPLOAD_MAX_BYTES = int(
    os.getenv("UPLOAD_MAX_BYTES", str(200 * 1024 * 1024))
)


VIDEO_ANALYSIS_MAX_DURATION_SECONDS = max(
    1.0,
    float(os.getenv("VIDEO_ANALYSIS_MAX_DURATION_SECONDS", "1800")),
)


# Keep Faster-Whisper feature extraction bounded to at most a 30-second clip.
VIDEO_TRANSCRIPTION_CHUNK_SECONDS = min(
    30.0,
    max(1.0, float(os.getenv("VIDEO_TRANSCRIPTION_CHUNK_SECONDS", "30"))),
)

VIDEO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS = max(
    0.0,
    min(
        5.0,
        VIDEO_TRANSCRIPTION_CHUNK_SECONDS / 2,
        float(os.getenv("VIDEO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS", "2")),
    ),
)


FRAMES_DIR = _configured_directory("FRAMES_DIR", BASE_DIR / "frames")


YOLO_MODEL_PATH = os.getenv(
    "YOLO_MODEL_PATH",
    str(BASE_DIR / "yolo11n.pt"),
)


SMART_SAMPLING_ENABLED = os.getenv(
    "SMART_SAMPLING_ENABLED",
    "true",
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


SMART_SAMPLING_COARSE_INTERVAL = float(
    os.getenv(
        "SMART_SAMPLING_COARSE_INTERVAL",
        "5.0",
    )
)


SMART_SAMPLING_VISUAL_THRESHOLD = float(
    os.getenv(
        "SMART_SAMPLING_VISUAL_THRESHOLD",
        "18.0",
    )
)


SMART_SAMPLING_REFINEMENT_WINDOW = float(
    os.getenv(
        "SMART_SAMPLING_REFINEMENT_WINDOW",
        "3.0",
    )
)


SMART_SAMPLING_REFINEMENT_INTERVAL = float(
    os.getenv(
        "SMART_SAMPLING_REFINEMENT_INTERVAL",
        "1.0",
    )
)


SMART_SAMPLING_MIN_FRAME_GAP = float(
    os.getenv(
        "SMART_SAMPLING_MIN_FRAME_GAP",
        "1.0",
    )
)


VIDEO_ANALYSIS_MAX_FRAMES = max(
    1,
    int(os.getenv("VIDEO_ANALYSIS_MAX_FRAMES", "30")),
)


VIDEO_ANALYSIS_FRAME_ANALYSIS_INTERVAL_SECONDS = max(
    0.1,
    float(os.getenv("VIDEO_ANALYSIS_FRAME_ANALYSIS_INTERVAL_SECONDS", "10")),
)


VIDEO_ANALYSIS_MAX_FRAME_DIMENSION = max(
    1,
    int(os.getenv("VIDEO_ANALYSIS_MAX_FRAME_DIMENSION", "1280")),
)


YOLO_MAX_DETECTIONS = 100


CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
            "http://localhost:5173,https://videomind.in",
    ).split(",")
    if origin.strip()
]
