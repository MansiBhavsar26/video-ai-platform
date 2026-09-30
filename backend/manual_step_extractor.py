from app.database import SessionLocal
from app.models import TranscriptSegment
from app.services.step_extractor import extract_steps


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
        f"TUTORIAL STEPS: {len(steps)}"
    )

    print()

    for step in steps:
        print(
            f"STEP {step['step']}"
        )

        print(
            f"ACTION: {step['action']}"
        )

        print(
            f"NAME: {step['name']}"
        )

        print(
            f"PATH: {step['path']}"
        )

        print(
            f"TIME: "
            f"{step['start_time']:.2f}s - "
            f"{step['end_time']:.2f}s"
        )

        print(
            f"INSTRUCTION: "
            f"{step['instruction']}"
        )

        print(
            f"CONFIDENCE: "
            f"{step['confidence']}"
        )

        print(
            f"VERIFIED: "
            f"{step['verified']}"
        )

        print(
            f"EVIDENCE SOURCE: "
            f"{step['evidence']['source']}"
        )

        print(
            f"EVIDENCE TEXT: "
            f"{step['evidence']['text']}"
        )

        print("-" * 60)

finally:
    db.close()