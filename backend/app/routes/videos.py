import os
import uuid
import logging
import tempfile

from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)

from sqlalchemy.orm import Session

from ..config import UPLOAD_MAX_BYTES
from ..database import get_db
from ..models import Video, Detection
from ..services.video_processor import get_video_info
from ..services.analyzer import analyze_video
from ..services.analysis_job import run_analysis_job
from ..services.video_url import acquire_video_from_url
from ..services.youtube import extract_youtube_video_id
from .youtube import (
    populate_youtube_analysis,
    transcript_http_error,
)
from ..services.youtube_transcript import YouTubeTranscriptError
from ..services.storage import (
    StorageError,
    get_local_storage,
    make_video_storage_key,
)


router = APIRouter(
    prefix="/videos",
    tags=["Videos"],
)

logger = logging.getLogger(__name__)


def _delete_storage_reference(storage, reference: str) -> None:
    try:
        storage.delete(reference)
    except StorageError:
        logger.exception("Unable to clean up stored video")



# ==================================================
# Upload Video
# ==================================================

@router.post("/upload")
def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="A filename is required.",
        )

    allowed_extensions = {
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
    }

    original_filename = Path(file.filename.replace("\\", "/")).name
    extension = Path(original_filename).suffix.lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported video format. "
                "Allowed formats: "
                + ", ".join(sorted(allowed_extensions))
            ),
        )

    content_type = (file.content_type or "").lower()
    allowed_content_types = {
        "video/mp4", "video/quicktime", "video/webm", "video/x-matroska",
        "application/octet-stream",
    }
    if content_type and content_type not in allowed_content_types:
        raise HTTPException(status_code=400, detail="Unsupported video content type.")

    storage = None
    storage_reference = None
    total_bytes = 0

    try:
        storage = get_local_storage()
        with tempfile.SpooledTemporaryFile(
            max_size=8 * 1024 * 1024,
            mode="w+b",
        ) as buffer:
            while chunk := file.file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > UPLOAD_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Video exceeds the upload size limit.")
                buffer.write(chunk)

            if total_bytes == 0:
                raise HTTPException(status_code=400, detail="The selected video file is empty.")

            buffer.seek(0)
            key = make_video_storage_key(uuid.uuid4().hex, extension)
            storage_reference = storage.save_stream(buffer, key)

        with storage.materialize(storage_reference) as local_path:
            info = get_video_info(local_path)
    except HTTPException:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        raise
    except StorageError as error:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        logger.exception("Video storage operation failed")
        raise HTTPException(
            status_code=503,
            detail="Video storage is unavailable.",
        ) from error

    except Exception:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)

        logger.exception("Unable to process uploaded video")

        raise HTTPException(
            status_code=400,
            detail="Invalid video file.",
        )

    video = Video(
        filename=original_filename,
        filepath=storage_reference,
        duration=info["duration"],
        fps=info["fps"],
        status="uploaded",
        source_type="upload",
    )

    try:
        db.add(video)
        db.commit()
        db.refresh(video)
    except Exception as error:
        db.rollback()
        _delete_storage_reference(storage, storage_reference)
        logger.exception("Unable to save uploaded video record")
        raise HTTPException(
            status_code=500,
            detail="Unable to save uploaded video.",
        ) from error

    return {
        "id": video.id,
        "filename": video.filename,
        "duration": video.duration,
        "fps": video.fps,
        "status": video.status,
        "source_type": video.source_type,
    }


@router.get("/{video_id}/status")
def get_video_status(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found.")
    return {"video_id": video.id, "status": video.status}

# ==================================================
# Analyze Video
# ==================================================

@router.post("/{video_id}/analyze")
def analyze_uploaded_video(
    video_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    video = (
        db.query(Video)
        .filter(Video.id == video_id)
        .first()
    )

    if not video:
        raise HTTPException(
            status_code=404,
            detail="Video not found",
        )

    if video.status == "processing":
        raise HTTPException(
            status_code=409,
            detail="Video analysis is already in progress.",
        )

    if video.filepath and not get_local_storage().exists(video.filepath):
        raise HTTPException(
            status_code=410,
            detail=(
                "The uploaded video is no longer available. "
                "Please upload the video again."
            ),
        )

    video.status = "processing"
    db.commit()

    background_tasks.add_task(
        run_analysis_job,
        video.id,
    )

    return {
        "video_id": video.id,
        "status": "processing",
        "message": "Video analysis started.",
    }

# ==================================================
# Add Video From URL
# ==================================================

def _youtube_response(video: Video, message: str):
    return {
        "id": video.id,
        "youtube_url": video.youtube_url,
        "youtube_video_id": video.youtube_video_id,
        "source_type": video.source_type,
        "status": video.status,
        "message": message,
    }


def _add_youtube_video_from_transcript(
    url: str,
    youtube_video_id: str,
    db: Session,
):
    existing_video = (
        db.query(Video)
        .filter(Video.youtube_video_id == youtube_video_id)
        .first()
    )

    if existing_video:
        if existing_video.status != "completed":
            try:
                existing_video.status = "processing"
                db.commit()
                populate_youtube_analysis(db, existing_video)
            except Exception as error:
                logger.exception(
                    "YouTube transcript analysis failed for video %s",
                    existing_video.id,
                )
                db.rollback()
                existing_video = db.query(Video).filter(
                    Video.id == existing_video.id
                ).first()
                if existing_video:
                    existing_video.status = "failed"
                    db.commit()
                if isinstance(error, YouTubeTranscriptError):
                    raise transcript_http_error(error) from error
                raise HTTPException(
                    status_code=422,
                    detail="Unable to analyze this YouTube tutorial.",
                ) from error

        return _youtube_response(
            existing_video,
            "This YouTube video already exists.",
        )

    video = Video(
        filename=f"youtube_{youtube_video_id}",
        filepath=None,
        duration=0,
        fps=0,
        status="uploaded",
        youtube_url=url,
        youtube_video_id=youtube_video_id,
        source_type="youtube",
    )

    db.add(video)
    db.commit()
    db.refresh(video)

    try:
        video.status = "processing"
        db.commit()
        populate_youtube_analysis(db, video)
    except Exception as error:
        logger.exception(
            "YouTube transcript analysis failed for video %s",
            video.id,
        )
        db.rollback()
        video = db.query(Video).filter(
            Video.id == video.id
        ).first()
        if video:
            video.status = "failed"
            db.commit()
        if isinstance(error, YouTubeTranscriptError):
            raise transcript_http_error(error) from error
        raise HTTPException(
            status_code=422,
            detail="Unable to analyze this YouTube tutorial.",
        ) from error

    return _youtube_response(
        video,
        "YouTube video added successfully.",
    )

@router.post("/url")
def add_video_from_url(
    url: str,
    db: Session = Depends(get_db),
):
    url = url.strip()

    if not url:
        raise HTTPException(
            status_code=400,
            detail="A video URL is required.",
        )

    if not (
        url.startswith("http://")
        or url.startswith("https://")
    ):
        raise HTTPException(
            status_code=400,
            detail="Only HTTP and HTTPS URLs are supported.",
        )

    youtube_video_id = extract_youtube_video_id(url)
    if youtube_video_id:
        return _add_youtube_video_from_transcript(
            url=url,
            youtube_video_id=youtube_video_id,
            db=db,
        )

    storage = None
    storage_reference = None
    try:
        storage = get_local_storage()
        result = acquire_video_from_url(
            url
        )

        source_filepath = result["filepath"]

        if not os.path.exists(source_filepath):
            raise ValueError(
                "Video acquisition completed, "
                "but the video file was not found."
            )

        info = get_video_info(
            source_filepath
        )

        extension = Path(source_filepath).suffix.lower()
        if extension not in {".mp4", ".mov", ".mkv", ".webm"}:
            extension = ".mp4"
        storage_reference = storage.save_file(
            source_filepath,
            make_video_storage_key(uuid.uuid4().hex, extension),
        )
        if storage_reference != source_filepath:
            os.remove(source_filepath)

    except StorageError as error:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        if "source_filepath" in locals() and os.path.exists(source_filepath):
            try:
                os.remove(source_filepath)
            except OSError:
                pass
        logger.exception("Unable to store acquired video")
        raise HTTPException(
            status_code=503,
            detail="Video storage is unavailable.",
        ) from error
    except Exception:

        if "source_filepath" in locals():
            if source_filepath and os.path.exists(source_filepath):
                try:
                    os.remove(source_filepath)
                except OSError:
                    pass
        if storage_reference:
            _delete_storage_reference(storage, storage_reference)

        logger.exception("Unable to acquire video from URL")
        raise HTTPException(
            status_code=400,
            detail="Unable to acquire video from URL.",
        )

    source_type = result.get(
        "source_type",
        "url",
    )

    video = Video(
        filename=(
            result.get("title")
            or Path(source_filepath).name
        ),
        filepath=storage_reference,
        duration=(
            info.get("duration")
            or result.get("duration")
            or 0
        ),
        fps=(
            info.get("fps")
            or result.get("fps")
            or 0
        ),
        status="uploaded",
        source_type=source_type,
        youtube_url=(
            url
            if source_type == "youtube"
            else None
        ),
        youtube_video_id=(
            result.get("external_id")
            if source_type == "youtube"
            else None
        ),
    )

    try:
        db.add(video)
        db.commit()
        db.refresh(video)
    except Exception as error:
        db.rollback()
        _delete_storage_reference(storage, storage_reference)
        logger.exception("Unable to save acquired video record")
        raise HTTPException(
            status_code=500,
            detail="Unable to save video.",
        ) from error

    return {
        "id": video.id,
        "filename": video.filename,
        "duration": video.duration,
        "fps": video.fps,
        "status": video.status,
        "source_type": video.source_type,
        "youtube_url": video.youtube_url,
        "youtube_video_id": video.youtube_video_id,
        "message": "Video added successfully.",
    }

# ==================================================
# Get Video Detections
# ==================================================

@router.get("/{video_id}/detections")
def get_video_detections(
    video_id: int,
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(
        Video.id == video_id
    ).first()

    if not video:
        return {
            "error": "Video not found"
        }

    detections = []

    for detection in video.detections:

        detections.append(
            {
                "id": detection.id,
                "timestamp": detection.timestamp,
                "label": detection.label,
                "confidence": detection.confidence,
                "x1": detection.x1,
                "y1": detection.y1,
                "x2": detection.x2,
                "y2": detection.y2,
            }
        )

    return {
        "video_id": video.id,
        "detections": detections,
    }


# ==================================================
# Get Video Details
# ==================================================

@router.get("/{video_id}")
def get_video(
    video_id: int,
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(
        Video.id == video_id
    ).first()

    if not video:
        return {
            "error": "Video not found"
        }

    return {
        "id": video.id,
        "filename": video.filename,
        "duration": video.duration,
        "fps": video.fps,
        "status": video.status,
        "description": video.description,
        "source_type": video.source_type,
        "youtube_url": video.youtube_url,
        "youtube_video_id": video.youtube_video_id,
        "created_at": video.created_at,
    }
