from app.database import SessionLocal
from app.models import TranscriptSegment

from app.services.transcript_chunker import (
    chunk_transcript,
)

from app.services.developer_action_detector import (
    detect_developer_actions,
)

from app.services.action_extractor import (
    extract_actions,
)


db = SessionLocal()

rows = (
    db.query(TranscriptSegment)
    .filter(
        TranscriptSegment.video_id == 17
    )
    .order_by(
        TranscriptSegment.start_time
    )
    .all()
)

segments = [
    {
        "start_time": row.start_time,
        "end_time": row.end_time,
        "text": row.text,
    }
    for row in rows
]

chunks = chunk_transcript(
    segments
)

print(
    "TOTAL CHUNKS:",
    len(chunks)
)

print("=" * 80)

total_actions = 0

for chunk in chunks:

    detected_actions = (
        detect_developer_actions(
            chunk
        )
    )

    for detected_action in detected_actions:

        actions = extract_actions(
            detected_action
        )

        for action in actions:

            total_actions += 1

            print(
                f"ACTION: {action['action']}"
            )

            print(
                f"VALUE: {action['value']}"
            )

            print(
                f"TIME: "
                f"{action['start_time']:.2f}s"
                f" - "
                f"{action['end_time']:.2f}s"
            )

            print(
                "EVIDENCE:"
            )

            print(
                action["evidence"]
            )

            print("-" * 80)


print(
    "EXTRACTED ACTIONS:",
    total_actions
)

db.close()