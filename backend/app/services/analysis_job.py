import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import VIDEO_ANALYSIS_MAX_DURATION_SECONDS
from ..database import SessionLocal
from ..models import Video, Detection
from .analyzer import analyze_video
from .transcription import transcribe_video, release_model as release_transcription_model
from .transcript_storage import save_transcript
from .developer_action_pipeline import build_tutorial_steps
from .tutorial_step_storage import save_tutorial_steps
from .storage import StorageError, get_video_storage
from .video_processor import validate_video_duration
from .analysis_diagnostics import analysis_stage, log_analysis_boundary


logger = logging.getLogger(__name__)


def run_analysis_job(video_id: int):
    db: Session = SessionLocal()

    try:
        log_analysis_boundary(video_id, "start")
        video = (
            db.query(Video)
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            logger.warning("[analysis] video=%s stage=lookup failed reason=not_found", video_id)
            return

        with analysis_stage(video_id, "validation"):
            validate_video_duration(
                video.duration,
                VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
            )

        video.status = "processing"
        db.commit()

        # -------------------------------------------------
        # STEP 1: Clear previous detections
        # -------------------------------------------------

        with analysis_stage(video_id, "previous_detection_cleanup"):
            db.query(Detection).filter(
                Detection.video_id == video.id
            ).delete(
                synchronize_session=False
            )
            db.commit()

        # -------------------------------------------------
        # STEP 2: Transcribe video
        # -------------------------------------------------

        storage = get_video_storage()
        with storage.frame_workspace(video.id) as frames_root:
            workspace = Path(frames_root) / str(video.id)
            try:
                # Remove frame leftovers from an interrupted/recovered attempt.
                shutil.rmtree(workspace, ignore_errors=True)
                workspace.mkdir(parents=True, exist_ok=True)
                with storage.materialize(video.filepath) as local_video_path:
                    with analysis_stage(video_id, "transcription") as metrics:
                        try:
                            transcript = transcribe_video(
                                local_video_path,
                                max_duration=VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
                                video_duration=video.duration,
                            )
                        except Exception:
                            release_transcription_model()
                            raise
                        transcript_segments = transcript["segments"]
                        metrics["segments"] = len(transcript_segments)

                    try:
                        with analysis_stage(video_id, "transcript_storage") as metrics:
                            save_transcript(
                                db=db,
                                video_id=video.id,
                                segments=transcript_segments,
                            )
                            metrics["segments"] = len(transcript_segments)
                    finally:
                        release_transcription_model()

                    with analysis_stage(video_id, "visual_analysis") as metrics:
                        result = analyze_video(
                            video_path=local_video_path,
                            video_id=video.id,
                            db=db,
                            video_duration=video.duration or 0,
                            transcript_segments=transcript_segments,
                            frames_root=frames_root,
                        )
                        metrics["frames"] = result.get("frames_processed", 0)
                        metrics["detections"] = result.get("detections_created", 0)
                        metrics["evidence_records"] = len(result.get("ocr_results", []))
                        metrics["fused_evidence_records"] = len(result.get("fused_evidence", []))
                    description = result["description"]
                    del result
            finally:
                shutil.rmtree(workspace, ignore_errors=True)

        video.description = description

        db.commit()

        # -------------------------------------------------
        # STEP 4: Extract tutorial steps
        # -------------------------------------------------

        with analysis_stage(video_id, "tutorial_steps") as metrics:
            tutorial_steps = build_tutorial_steps(transcript_segments)
            metrics["steps"] = len(tutorial_steps)

        # -------------------------------------------------
        # STEP 5: Save tutorial steps
        # -------------------------------------------------

        with analysis_stage(video_id, "tutorial_step_storage") as metrics:
            save_tutorial_steps(
                db=db,
                video_id=video.id,
                steps=tutorial_steps,
            )
            metrics["steps"] = len(tutorial_steps)

        # -------------------------------------------------
        # STEP 6: Mark analysis completed
        # -------------------------------------------------

        video.status = "completed"
        db.commit()
        log_analysis_boundary(video_id, "completed")

    except Exception as error:
        logger.error(
            "[analysis] video=%s stage=job failed error_type=%s storage_error=%s",
            video_id,
            type(error).__name__,
            isinstance(error, StorageError),
        )

        try:
            db.rollback()
            video = (
                db.query(Video)
                .filter(Video.id == video_id)
                .first()
            )

            if video:
                video.status = "failed"
                db.commit()
        except Exception as status_error:
            db.rollback()
            logger.error(
                "[analysis] video=%s stage=status_update failed error_type=%s",
                video_id,
                type(status_error).__name__,
            )

    finally:
        db.close()
