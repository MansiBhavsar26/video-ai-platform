from app.database import SessionLocal
from app.models import TranscriptSegment

from app.services.action_context import (
    build_action_context,
)

from app.services.action_reconstructor import (
    reconstruct_react_setup,
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


actions = reconstruct_react_setup(
    context
)


print(
    "ACTIONS FOUND:",
    len(actions),
)

print("=" * 80)


for index, action in enumerate(
    actions,
    start=1,
):

    print(
        f"ACTION {index}"
    )

    print(
        "TYPE:",
        action["action"],
    )

    print(
        "VALUE:",
        action["value"],
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