from app.database import SessionLocal
from app.models import TranscriptSegment
from app.services.transcript_chunker import chunk_transcript


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
    "SEGMENTS:",
    len(segments)
)

print(
    "CHUNKS:",
    len(chunks)
)

print("=" * 80)

for chunk in chunks[:20]:

    print(
        "["
        f"{chunk['start_time']:.2f}s"
        " - "
        f"{chunk['end_time']:.2f}s"
        "]"
    )

    print(
        chunk["text"][:500]
    )

    print("-" * 80)


db.close()