from app.database import SessionLocal
from app.models import TranscriptSegment


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


context = [
    segment
    for segment in segments
    if (
        segment["end_time"] >= 1890
        and segment["start_time"] <= 1920
    )
]


print("=" * 80)
print("APP.JS EDIT CONTEXT")
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


db.close()