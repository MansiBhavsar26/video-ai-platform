from app.database import SessionLocal
from app.models import TranscriptSegment

from app.services.action_context import (
    build_action_context,
    combine_context_text,
)

from app.services.technical_normalizer import (
    reconstruct_npm_install,
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


router_segments = [
    segment
    for segment in segments
    if (
        segment["end_time"] >= 1860
        and segment["start_time"] <= 1890
    )
]


context_text = combine_context_text(
    router_segments
)

print("=" * 80)
print("ROUTER CONTEXT")
print("=" * 80)

print(context_text)

print()
print("=" * 80)
print("NORMALIZED COMMAND")
print("=" * 80)

command = reconstruct_npm_install(
    context_text
)

print(
    command
    if command
    else "NOT FOUND"
)


db.close()