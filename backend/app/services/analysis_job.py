import traceback
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
from .storage import StorageError, get_local_storage
from .video_processor import validate_video_duration


def run_analysis_job(video_id: int):
    db: Session = SessionLocal()

    try:
        video = (
            db.query(Video)
            .filter(Video.id == video_id)
            .first()
        )

        if not video:
            print(
                f"Video {video_id} not found."
            )
            return

        print(
            f"Starting analysis for video {video_id}..."
        )

        validate_video_duration(
            video.duration,
            VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
        )

        video.status = "processing"
        db.commit()

        # -------------------------------------------------
        # STEP 1: Clear previous detections
        # -------------------------------------------------

        db.query(Detection).filter(
            Detection.video_id == video.id
        ).delete(
            synchronize_session=False
        )

        db.commit()

        # -------------------------------------------------
        # STEP 2: Transcribe video
        # -------------------------------------------------

        print(
            f"Starting transcription for video {video_id}..."
        )

        storage = get_local_storage()
        with storage.frame_workspace(video.id) as frames_root:
            workspace = Path(frames_root) / str(video.id)
            try:
                # Remove frame leftovers from an interrupted/recovered attempt.
                shutil.rmtree(workspace, ignore_errors=True)
                workspace.mkdir(parents=True, exist_ok=True)
                with storage.materialize(video.filepath) as local_video_path:
                    try:
                        transcript = transcribe_video(
                            local_video_path,
                            max_duration=VIDEO_ANALYSIS_MAX_DURATION_SECONDS,
                            video_duration=video.duration,
                        )
                    except Exception:
                        release_transcription_model()
                        raise

                    try:
                        transcript_segments = transcript["segments"]

                        print(
                            f"Transcription completed. "
                            f"Segments: {len(transcript_segments)}"
                        )

                        save_transcript(
                            db=db,
                            video_id=video.id,
                            segments=transcript_segments,
                        )
                        print(f"Transcript saved for video {video_id}.")
                    finally:
                        release_transcription_model()

                    # -------------------------------------------------
                    # STEP 3: Analyze video
                    # -------------------------------------------------

                    print(
                        f"Running visual analysis for video {video_id}..."
                    )
                    result = analyze_video(
                        video_path=local_video_path,
                        video_id=video.id,
                        db=db,
                        video_duration=video.duration or 0,
                        transcript_segments=transcript_segments,
                        frames_root=frames_root,
                    )
            finally:
                shutil.rmtree(workspace, ignore_errors=True)

        video.description = result[
            "description"
        ]

        db.commit()

        print(
            f"Visual analysis completed for video {video_id}."
        )

        # -------------------------------------------------
        # STEP 4: Extract tutorial steps
        # -------------------------------------------------

        print(
            f"Extracting tutorial steps "
            f"for video {video_id}..."
        )

        tutorial_steps = build_tutorial_steps(
            transcript_segments
        )

        print(
            f"Tutorial steps extracted: "
            f"{len(tutorial_steps)}"
        )

        # -------------------------------------------------
        # STEP 5: Save tutorial steps
        # -------------------------------------------------

        save_tutorial_steps(
            db=db,
            video_id=video.id,
            steps=tutorial_steps,
        )

        print(
            f"Tutorial steps saved for video {video_id}."
        )

        # -------------------------------------------------
        # STEP 6: Mark analysis completed
        # -------------------------------------------------

        video.status = "completed"
        db.commit()

        print(
            f"Analysis completed successfully "
            f"for video {video_id}."
        )

    except Exception as error:
        if isinstance(error, StorageError):
            print(f"Analysis storage operation failed for video {video_id}.")
        else:
            print(
                f"Analysis failed for video {video_id}: "
                f"{error}"
            )

        traceback.print_exc()

        db.rollback()

        video = (
            db.query(Video)
            .filter(Video.id == video_id)
            .first()
        )

        if video:
            video.status = "failed"
            db.commit()

    finally:
        db.close()
