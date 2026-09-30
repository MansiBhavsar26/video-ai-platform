from app.database import SessionLocal
from app.models import TranscriptSegment, TutorialStep
from app.services.step_extractor import extract_steps
from app.services.tutorial_step_storage import save_tutorial_steps


db = SessionLocal()

try:
    segments = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.video_id == 14
        )
        .order_by(
            TranscriptSegment.start_time
        )
        .all()
    )

    transcript_segments = [
        {
            "start_time": segment.start_time,
            "end_time": segment.end_time,
            "text": segment.text,
        }
        for segment in segments
    ]

    print(
        f"TRANSCRIPT SEGMENTS: "
        f"{len(transcript_segments)}"
    )

    steps = extract_steps(
        transcript_segments
    )

    print(
        f"EXTRACTED STEPS: {len(steps)}"
    )

    saved_steps = save_tutorial_steps(
        db=db,
        video_id=14,
        steps=steps,
    )

    print(
        f"SAVED STEPS: {len(saved_steps)}"
    )

    print()

    database_steps = (
        db.query(TutorialStep)
        .filter(
            TutorialStep.video_id == 14
        )
        .order_by(
            TutorialStep.step_number
        )
        .all()
    )

    print(
        f"DATABASE STEPS: "
        f"{len(database_steps)}"
    )

    print()

    for step in database_steps:
        print(
            f"STEP {step.step_number}"
        )

        print(
            f"ACTION: {step.action}"
        )

        print(
            f"NAME: {step.name}"
        )

        print(
            f"PATH: {step.path}"
        )

        print(
            f"CONFIDENCE: "
            f"{step.confidence}"
        )

        print(
            f"VERIFIED: "
            f"{step.verified}"
        )

        print(
            f"EVIDENCE SOURCE: "
            f"{step.evidence_source}"
        )

        print(
            f"EVIDENCE TEXT: "
            f"{step.evidence_text}"
        )

        print("-" * 60)

finally:
    db.close()