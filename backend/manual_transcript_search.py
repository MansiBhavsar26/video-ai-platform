from app.database import SessionLocal
from app.services.transcript_search import search_transcript


db = SessionLocal()

try:
    question = (
        "Where does the tutorial create "
        "the components folder?"
    )

    print(
        f"QUESTION: {question}"
    )

    print()

    results = search_transcript(
        db=db,
        video_id=14,
        question=question,
        limit=5,
    )

    print(
        f"RESULTS FOUND: {len(results)}"
    )

    print()

    for index, result in enumerate(
        results,
        start=1,
    ):
        print(
            f"RESULT {index}"
        )

        print(
            f"SCORE: {result['score']}"
        )

        print(
            f"TIME: "
            f"{result['start_time']:.2f}s - "
            f"{result['end_time']:.2f}s"
        )

        print(
            f"TEXT: "
            f"{result['text']}"
        )

        print("-" * 60)

finally:
    db.close()