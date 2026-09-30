from app.database import SessionLocal
from app.models import TranscriptSegment

from app.services.file_action_extractor import (
    extract_file_edit_actions,
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


# --------------------------------------------------
# App.js routing example
# --------------------------------------------------

context = [
    segment
    for segment in segments
    if (
        segment["end_time"] >= 1885
        and segment["start_time"] <= 1910
    )
]


actions = extract_file_edit_actions(
    context
)


print("=" * 80)
print("FILE ACTIONS")
print("=" * 80)

print(
    "ACTIONS FOUND:",
    len(actions),
)

print()


for action in actions:

    print(
        "ACTION:",
        action["action"],
    )

    print(
        "FILE:",
        action["value"],
    )

    print(
        "OPERATION:",
        action["operation"],
    )

    print(
        f"TIME: "
        f"{action['start_time']:.2f}s"
        f" - "
        f"{action['end_time']:.2f}s"
    )

    print(
        "CONFIDENCE:",
        action["confidence"],
    )

    print(
        "EVIDENCE:"
    )

    print(
        action["evidence"]
    )

    print("-" * 80)


db.close()