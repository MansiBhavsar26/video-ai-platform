import os
import uuid
import logging
import tempfile
import shutil

from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import (
    UPLOAD_MAX_BYTES,
    VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
)
from ..database import get_db
from ..models import Video, Detection
from ..services.video_processor import (
    VideoDurationError,
    get_video_info,
    validate_video_duration,
)
from ..services.analyzer import analyze_video
from ..services.analysis_job import run_analysis_job
from ..services.video_url import VideoTooLargeError, acquire_video_from_url
from ..services.youtube import extract_youtube_video_id
from .youtube import (
    populate_youtube_analysis,
    transcript_http_error,
)
from ..services.youtube_transcript import YouTubeTranscriptError
from ..services.storage import (
    StorageError,
    get_video_storage,
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
    except StorageError as error:
        logger.error(
            "Unable to clean up stored video error_type=%s",
            type(error).__name__,
        )


def _upload_limit_message() -> str:
    maximum_mb = UPLOAD_MAX_BYTES / (1024 * 1024)
    if maximum_mb >= 1:
        size_label = f"{maximum_mb:g} MB"
    else:
        size_label = f"{UPLOAD_MAX_BYTES} bytes"
    return f"Video exceeds the current {size_label} upload limit."


def _claim_analysis(db: Session, video_id: int) -> bool:
    result = db.execute(
        update(Video)
        .where(Video.id == video_id, Video.status != "processing")
        .values(status="processing")
    )
    return result.rowcount == 1



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
    temporary_upload_path = None
    total_bytes = 0

    try:
        with tempfile.NamedTemporaryFile(
            mode="w+b",
            suffix=extension,
            prefix="videomind-upload-",
            delete=False,
        ) as buffer:
            temporary_upload_path = buffer.name
            while chunk := file.file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > UPLOAD_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=_upload_limit_message(),
                    )
                buffer.write(chunk)

            if total_bytes == 0:
                raise HTTPException(status_code=400, detail="The selected video file is empty.")

        info = get_video_info(temporary_upload_path)
        duration = validate_video_duration(
            info.get("duration"),
            VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
        )

        storage = get_video_storage()
        with open(temporary_upload_path, "rb") as buffer:
            key = make_video_storage_key(uuid.uuid4().hex, extension)
            storage_reference = storage.save_stream(buffer, key)
    except HTTPException:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        raise
    except VideoDurationError as error:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        raise HTTPException(status_code=422, detail=str(error)) from error
    except StorageError as error:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        logger.error(
            "Video storage operation failed error_type=%s",
            type(error).__name__,
        )
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
    finally:
        if temporary_upload_path:
            try:
                os.remove(temporary_upload_path)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Unable to clean temporary upload file")

    video = Video(
        filename=original_filename,
        filepath=storage_reference,
        duration=duration,
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
    response = {"video_id": video.id, "status": video.status}
    if video.status == "failed":
        try:
            source_exists = (
                get_video_storage().exists(video.filepath)
                if video.filepath
                else True
            )
        except StorageError as error:
            logger.error(
                "Video storage unavailable during status check error_type=%s",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="Video storage is unavailable.",
            ) from error

        if video.filepath and not source_exists:
            response["message"] = (
                "The uploaded video is no longer available. "
                "Please upload the video again."
            )
        elif video.filepath:
            try:
                validate_video_duration(
                    video.duration,
                    VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
                )
            except VideoDurationError as error:
                response["message"] = str(error)
            else:
                response["message"] = (
                    "Video analysis failed. Check the video and try again."
                )
        else:
            response["message"] = (
                "Video analysis failed. Check the video and try again."
            )
    return response

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

    if video.filepath:
        try:
            source_exists = get_video_storage().exists(video.filepath)
        except StorageError as error:
            logger.error(
                "Video storage unavailable before analysis error_type=%s",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="Video storage is unavailable.",
            ) from error
        if not source_exists:
            raise HTTPException(
                status_code=410,
                detail=(
                    "The uploaded video is no longer available. "
                    "Please upload the video again."
                ),
            )

    try:
        validate_video_duration(
            video.duration,
            VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
        )
    except VideoDurationError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    if not _claim_analysis(db, video.id):
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Video analysis is already in progress.",
        )

    try:
        db.commit()
    except Exception as error:
        db.rollback()
        logger.exception("Unable to claim video analysis")
        raise HTTPException(
            status_code=503,
            detail="Unable to start video analysis.",
        ) from error

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
    source_temporary_directory = None
    try:
        storage = get_video_storage()
        result = acquire_video_from_url(
            url,
            max_bytes=UPLOAD_MAX_BYTES,
        )

        source_filepath = result["filepath"]
        source_temporary_directory = result.get("temporary_directory")

        if not os.path.exists(source_filepath):
            raise ValueError(
                "Video acquisition completed, "
                "but the video file was not found."
            )

        info = get_video_info(source_filepath)
        duration = validate_video_duration(
            info.get("duration"),
            VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
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

    except VideoTooLargeError as error:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        if "source_filepath" in locals() and os.path.exists(source_filepath):
            try:
                os.remove(source_filepath)
            except OSError:
                pass
        raise HTTPException(
            status_code=413,
            detail=_upload_limit_message(),
        ) from error
    except VideoDurationError as error:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        if "source_filepath" in locals() and os.path.exists(source_filepath):
            try:
                os.remove(source_filepath)
            except OSError:
                pass
        raise HTTPException(status_code=422, detail=str(error)) from error
    except StorageError as error:
        if storage and storage_reference:
            _delete_storage_reference(storage, storage_reference)
        if "source_filepath" in locals() and os.path.exists(source_filepath):
            try:
                os.remove(source_filepath)
            except OSError:
                pass
        logger.error(
            "Unable to store acquired video error_type=%s",
            type(error).__name__,
        )
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
    finally:
        if source_temporary_directory:
            shutil.rmtree(source_temporary_directory, ignore_errors=True)

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
            duration
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
