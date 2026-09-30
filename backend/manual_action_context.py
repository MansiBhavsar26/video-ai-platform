from app.database import SessionLocal
from app.models import TranscriptSegment

from app.services.action_context import (
    build_action_context,
    combine_context_text,
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


context = build_action_context(
    segments=segments,
    action_start=133.41,
    action_end=162.96,
    padding_seconds=20.0,
)

print(
    "CONTEXT SEGMENTS:",
    len(context),
)

print("=" * 80)

for segment in context:

    print(
        f"[{segment['start_time']:.2f}s"
        f" - "
        f"{segment['end_time']:.2f}s]"
    )

    print(
        segment["text"]
    )

    print("-" * 80)


print("=" * 80)

combined = combine_context_text(
    context
)

print(
    "COMBINED CONTEXT:"
)

print(
    combined
)

db.close()