import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import TranscriptSegment, TutorialStep, Video, VideoEvidence
from app.routes.ask import router as ask_router
from app.services import video_qa


@pytest.fixture
def qa_store():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()

    first = Video(
        filename="first.mp4",
        duration=120,
        fps=30,
        status="completed",
        source_type="upload",
    )
    second = Video(
        filename="second.mp4",
        duration=120,
        fps=30,
        status="completed",
        source_type="upload",
    )
    db.add_all([first, second])
    db.flush()
    first_id, second_id = first.id, second.id

    db.add_all(
        [
            TranscriptSegment(
                video_id=first_id,
                start_time=12.5,
                end_time=18.75,
                text="Install React Router using npm install react-router-dom.",
            ),
            TranscriptSegment(
                video_id=second_id,
                start_time=88,
                end_time=93,
                text="React Router install secret-video-two-marker.",
            ),
            TutorialStep(
                video_id=first_id,
                step_number=1,
                action="run_command",
                confidence=0.9,
                verified=True,
                instruction="Run npm install react-router-dom to install React Router.",
                start_time=12.5,
                end_time=18.75,
                evidence_source="transcript",
                evidence_text="Install React Router using npm install react-router-dom.",
            ),
            VideoEvidence(
                video_id=first_id,
                timestamp=14.0,
                evidence_type="command",
                text="npm install react-router-dom",
                source="video_frame",
                confidence=0.85,
            ),
        ]
    )
    db.commit()

    app = FastAPI()
    app.include_router(ask_router)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        yield SimpleNamespace(
            db=db,
            client=client,
            first_id=first_id,
            second_id=second_id,
        )
    finally:
        client.close()
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _install_answer_mock(monkeypatch, answer=None, evidence_ids=None):
    calls = []
    answer = answer or "Run npm install react-router-dom to add React Router."

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            payload = json.loads(kwargs["input"])
            citations = evidence_ids or [payload["evidence"][0]["context_id"]]
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "answerable": True,
                        "answer": answer,
                        "evidence_ids": citations,
                    }
                )
            )

    class FakeOpenAI:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(video_qa, "OpenAI", FakeOpenAI)
    return calls


def test_successful_question_returns_direct_answer_and_structured_evidence(
    qa_store, monkeypatch
):
    calls = _install_answer_mock(monkeypatch)

    response = qa_store.client.post(
        f"/videos/{qa_store.first_id}/ask",
        json={"question": "How do I install React Router?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answerable"] is True
    assert payload["answer"] == "Run npm install react-router-dom to add React Router."
    assert not payload["answer"].startswith("The most relevant section")
    assert payload["evidence"]
    assert all("start_time" in item and "end_time" in item for item in payload["evidence"])
    assert calls[0]["model"] == video_qa.DEFAULT_MODEL


def test_no_relevant_context_returns_not_found_without_calling_model(
    qa_store, monkeypatch
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = qa_store.client.post(
        f"/videos/{qa_store.first_id}/ask",
        json={"question": "Who won the lunar tennis tournament?"},
    )

    assert response.status_code == 200
    assert response.json()["answerable"] is False
    assert "could not find enough relevant information" in response.json()["answer"].lower()
    assert response.json()["evidence"] == []


def test_transcript_timestamps_are_preserved(qa_store):
    context = video_qa.build_video_context(
        qa_store.db,
        qa_store.first_id,
        "npm install react-router-dom",
    )
    transcript = next(item for item in context if item["source_type"] == "transcript")

    assert transcript["start_time"] == 12.5
    assert transcript["end_time"] == 18.75
    assert transcript["relevance"] > 0


def test_tutorial_steps_contribute_context(qa_store):
    context = video_qa.build_video_context(
        qa_store.db,
        qa_store.first_id,
        "How do I install React Router?",
    )
    step = next(item for item in context if item["source_type"] == "tutorial_step")

    assert "npm install react-router-dom" in step["instruction"]
    assert step["source"] == "transcript"
    assert (step["start_time"], step["end_time"]) == (12.5, 18.75)


def test_video_evidence_contributes_context_and_keeps_point_timestamp(qa_store):
    context = video_qa.build_video_context(
        qa_store.db,
        qa_store.first_id,
        "npm install react-router-dom",
    )
    frame_evidence = next(
        item for item in context if item["source_type"] == "video_evidence"
    )

    assert frame_evidence["text"] == "npm install react-router-dom"
    assert frame_evidence["source"] == "video_frame"
    assert frame_evidence["start_time"] == frame_evidence["end_time"] == 14.0


def test_retrieval_is_isolated_to_requested_video(qa_store):
    context = video_qa.build_video_context(
        qa_store.db,
        qa_store.first_id,
        "How do I install React Router?",
    )
    serialized = json.dumps(context)

    assert "secret-video-two-marker" not in serialized
    other_video_context = video_qa.build_video_context(
        qa_store.db,
        qa_store.second_id,
        "How do I install React Router?",
    )
    assert "secret-video-two-marker" in json.dumps(other_video_context)


def test_blank_question_is_rejected(qa_store):
    response = qa_store.client.post(
        f"/videos/{qa_store.first_id}/ask",
        json={"question": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Question cannot be empty"


def test_missing_video_is_rejected(qa_store):
    response = qa_store.client.post(
        "/videos/99999/ask",
        json={"question": "How do I install React Router?"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Video not found"


def test_context_is_bounded_and_sorted_by_relevance(qa_store):
    for index in range(30):
        qa_store.db.add(
            TranscriptSegment(
                video_id=qa_store.first_id,
                start_time=100 + index,
                end_time=101 + index,
                text=(
                    "Run npm run dev to start the JavaScript application. "
                    + ("background details " * 100)
                ),
            )
        )
    qa_store.db.add(
        TranscriptSegment(
            video_id=qa_store.first_id,
            start_time=5,
            end_time=8,
            text="Run npm run dev",
        )
    )
    qa_store.db.commit()

    context = video_qa.build_video_context(
        qa_store.db,
        qa_store.first_id,
        "How do I run npm run dev?",
    )

    assert len(context) <= video_qa.MAX_CONTEXT_ITEMS
    assert len(json.dumps(context, ensure_ascii=False)) <= video_qa.MAX_CONTEXT_CHARS
    assert context[0]["text"] == "Run npm run dev"
    assert context[0]["relevance"] >= context[-1]["relevance"]


def test_model_cannot_cite_context_outside_the_retrieved_package(
    qa_store, monkeypatch
):
    _install_answer_mock(monkeypatch, evidence_ids=[999])

    response = qa_store.client.post(
        f"/videos/{qa_store.first_id}/ask",
        json={"question": "How do I install React Router?"},
    )

    assert response.status_code == 200
    assert response.json()["answerable"] is False
    assert response.json()["evidence"] == []
