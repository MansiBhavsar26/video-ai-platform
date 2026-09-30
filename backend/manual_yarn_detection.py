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

print("=" * 80)
print("YARN START SEGMENTS")
print("=" * 80)

found = 0

for row in rows:

    if "yarn" in row.text.lower():

        print(
            f"{row.start_time:.2f}s"
            f" - "
            f"{row.end_time:.2f}s"
        )

        print(row.text)

        print("-" * 80)

        found += 1

print(
    "FOUND:",
    found
)

db.close()