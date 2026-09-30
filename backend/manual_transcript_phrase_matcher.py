from app.database import SessionLocal
from app.models import TranscriptSegment

from app.services.transcript_phrase_matcher import (
    find_phrase_across_segments,
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
# Only inspect the React project setup section.
# --------------------------------------------------

setup_segments = [
    segment
    for segment in segments
    if (
        segment["end_time"] >= 109
        and segment["start_time"] <= 170
    )
]


phrases = [
    "create react app",
    "cd react tutorial",
    "yarn start",
]


for phrase in phrases:

    print("=" * 80)

    print(
        "SEARCH:",
        phrase,
    )

    result = find_phrase_across_segments(
        segments=setup_segments,
        phrase=phrase,
    )

    if result:

        print(
            "FOUND:",
            result["phrase"],
        )

        print(
            f"TIME: "
            f"{result['start_time']:.2f}s"
            f" - "
            f"{result['end_time']:.2f}s"
        )

        print(
            "EVIDENCE:"
        )

        print(
            result["evidence"]
        )

    else:

        print(
            "NOT FOUND"
        )


db.close()