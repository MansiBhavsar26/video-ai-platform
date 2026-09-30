from app.database import SessionLocal
from app.models import TranscriptSegment

from app.services.action_context import (
    build_action_context,
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


# Router installation section
router_segments = [
    segment
    for segment in segments
    if (
        segment["end_time"] >= 1840
        and segment["start_time"] <= 1920
    )
]


print("=" * 80)
print("ROUTER INSTALLATION CONTEXT")
print("=" * 80)

for segment in router_segments:

    print(
        f"[{segment['start_time']:.2f}s"
        f" - "
        f"{segment['end_time']:.2f}s]"
    )

    print(
        segment["text"]
    )

    print("-" * 80)


db.close()