import asyncio
import time
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from app.database import Base
from app.models import (
    Detection,
    TranscriptSegment,
    TutorialStep,
    Video,
    VideoEvidence,
)
from app.services import analysis_job, analysis_recovery
from app.services.evidence_storage import save_video_evidence
from app.services.storage import LocalStorageBackend, make_video_storage_key


@pytest.fixture
def recovery_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'recovery-test.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    yield testing_session
    Base.metadata.drop_all(engine)
    engine.dispose()


def _add_video(
    session_factory,
    *,
    video_id,
    status,
    source_type="upload",
    filepath=None,
    duration=2,
):
    db = session_factory()
    video = Video(
        id=video_id,
        filename=f"video-{video_id}.mp4",
        filepath=filepath,
        duration=duration,
        fps=24,
        status=status,
        source_type=source_type,
    )
    db.add(video)
    db.commit()
    db.close()
    return video_id


def _interrupted_id(session_factory, monkeypatch, **video_options):
    video_id = video_options.pop("video_id", 21)
    _add_video(
        session_factory,
        video_id=video_id,
        **video_options,
    )
    monkeypatch.setattr(analysis_recovery, "SessionLocal", session_factory)
    return video_id


def test_processing_local_upload_is_discovered(recovery_db, monkeypatch, tmp_path):
    source = tmp_path / "uploads" / "source.mp4"
    source.parent.mkdir()
    source.write_bytes(b"local video")
    video_id = _interrupted_id(
        recovery_db,
        monkeypatch,
        video_id=31,
        status="processing",
        source_type="upload",
        filepath=str(source),
    )

    assert analysis_recovery.find_interrupted_analysis_video_ids() == [video_id]


@pytest.mark.parametrize(
    "video_id,status,source_type,filepath",
    [
        (32, "processing", "youtube", None),
        (33, "completed", "upload", "C:/uploads/completed.mp4"),
        (34, "failed", "upload", "C:/uploads/failed.mp4"),
    ],
)
def test_ineligible_videos_are_ignored(
    recovery_db,
    monkeypatch,
    video_id,
    status,
    source_type,
    filepath,
):
    _interrupted_id(
        recovery_db,
        monkeypatch,
        video_id=video_id,
        status=status,
        source_type=source_type,
        filepath=filepath,
    )

    assert analysis_recovery.find_interrupted_analysis_video_ids() == []


def test_multiple_jobs_call_existing_analysis_sequentially(monkeypatch):
    calls = []
    active = 0
    max_active = 0

    monkeypatch.setattr(
        analysis_recovery,
        "find_interrupted_analysis_video_ids",
        lambda: [41, 42, 43],
    )

    def mock_existing_analysis(video_id):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        time.sleep(0.02)
        calls.append(video_id)
        active -= 1

    monkeypatch.setattr(
        analysis_recovery,
        "run_analysis_job",
        mock_existing_analysis,
    )

    asyncio.run(analysis_recovery.recover_interrupted_analyses())

    assert calls == [41, 42, 43]
    assert max_active == 1


def test_startup_returns_without_waiting_for_analysis(monkeypatch):
    from app import main

    async def blocked_recovery():
        await asyncio.Event().wait()

    monkeypatch.setattr(
        analysis_recovery,
        "recover_interrupted_analyses",
        blocked_recovery,
    )

    async def run_startup_check():
        await asyncio.wait_for(main.recover_interrupted_video_analyses(), timeout=0.2)
        await asyncio.sleep(0)
        task = main.app.state.analysis_recovery_task
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run_startup_check())


def test_recovery_scheduler_prevents_duplicate_task_in_one_process(monkeypatch):
    from types import SimpleNamespace

    async def blocked_recovery():
        await asyncio.Event().wait()

    monkeypatch.setattr(
        analysis_recovery,
        "recover_interrupted_analyses",
        blocked_recovery,
    )
    app = SimpleNamespace(state=SimpleNamespace())

    async def schedule_twice():
        first = analysis_recovery.schedule_interrupted_analysis_recovery(app)
        await asyncio.sleep(0)
        second = analysis_recovery.schedule_interrupted_analysis_recovery(app)
        assert first is second
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

    asyncio.run(schedule_twice())


def test_missing_source_video_becomes_failed_not_stuck(
    recovery_db,
    monkeypatch,
    tmp_path,
):
    upload_dir = tmp_path / "uploads"
    storage = LocalStorageBackend(upload_dir, tmp_path / "frames")
    missing_path = storage._path_for_key("videos/missing/source.mp4")
    _interrupted_id(
        recovery_db,
        monkeypatch,
        video_id=51,
        status="processing",
        source_type="upload",
        filepath=str(missing_path),
    )
    monkeypatch.setattr(analysis_job, "SessionLocal", recovery_db)
    monkeypatch.setattr(analysis_job, "get_local_storage", lambda: storage)
    monkeypatch.setattr(analysis_job.traceback, "print_exc", lambda: None)

    asyncio.run(analysis_recovery.recover_interrupted_analyses())

    db = recovery_db()
    try:
        video = db.query(Video).filter(Video.id == 51).one()
        assert video.status == "failed"
    finally:
        db.close()


@pytest.mark.parametrize("duration", [0, None, float("nan"), 1801])
def test_recovery_rejects_unknown_duration_before_transcription(
    recovery_db,
    monkeypatch,
    tmp_path,
    duration,
):
    storage = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    source_path = storage.save_stream(
        BytesIO(b"synthetic source"),
        make_video_storage_key("unknown-duration", ".mp4"),
    )
    _add_video(
        recovery_db,
        video_id=52,
        status="processing",
        filepath=source_path,
        duration=duration,
    )
    monkeypatch.setattr(analysis_job, "SessionLocal", recovery_db)
    monkeypatch.setattr(analysis_job, "get_local_storage", lambda: storage)
    monkeypatch.setattr(analysis_job.traceback, "print_exc", lambda: None)
    monkeypatch.setattr(
        analysis_job,
        "transcribe_video",
        lambda *args, **kwargs: pytest.fail("invalid duration reached transcription"),
    )

    analysis_job.run_analysis_job(52)

    db = recovery_db()
    try:
        assert db.query(Video).filter(Video.id == 52).one().status == "failed"
    finally:
        db.close()


def test_synthetic_video_four_recovers_and_rerun_replaces_results(
    recovery_db,
    monkeypatch,
    tmp_path,
):
    storage = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    video_path = storage.save_stream(
        BytesIO(b"small deterministic video"),
        make_video_storage_key("synthetic-four", ".mp4"),
    )
    _add_video(
        recovery_db,
        video_id=4,
        status="processing",
        source_type="upload",
        filepath=video_path,
    )
    monkeypatch.setattr(analysis_recovery, "SessionLocal", recovery_db)
    monkeypatch.setattr(analysis_job, "SessionLocal", recovery_db)
    monkeypatch.setattr(analysis_job, "get_local_storage", lambda: storage)
    lifecycle = []

    def transcribe(path, *, max_duration, video_duration):
        assert max_duration == analysis_job.VIDEO_ANALYSIS_MAX_DURATION_SECONDS
        assert video_duration == 2
        lifecycle.append("transcribe")
        return {
            "segments": [
                {"start_time": 0.0, "end_time": 1.0, "text": "Run npm install."}
            ]
        }

    def release_transcriber():
        db = recovery_db()
        try:
            assert db.query(TranscriptSegment).filter(
                TranscriptSegment.video_id == 4
            ).count() == 1
        finally:
            db.close()
        lifecycle.append("whisper_released")

    monkeypatch.setattr(analysis_job, "transcribe_video", transcribe)
    monkeypatch.setattr(
        analysis_job,
        "release_transcription_model",
        release_transcriber,
    )

    def deterministic_visual_analysis(video_path, video_id, db, **kwargs):
        assert lifecycle[-1] == "whisper_released"
        lifecycle.append("visual_analysis")
        temporary_frame = Path(kwargs["frames_root"]) / str(video_id) / "sample.jpg"
        temporary_frame.parent.mkdir(parents=True, exist_ok=True)
        temporary_frame.write_bytes(b"generated frame")
        db.add(
            Detection(
                video_id=video_id,
                timestamp=0,
                label="screen",
                confidence=0.9,
                x1=0,
                y1=0,
                x2=10,
                y2=10,
            )
        )
        save_video_evidence(
            db,
            video_id,
            [{"timestamp": 0, "text": "Install dependencies", "confidence": 0.9}],
        )
        return {"description": "Synthetic local test video"}

    monkeypatch.setattr(analysis_job, "analyze_video", deterministic_visual_analysis)
    monkeypatch.setattr(
        analysis_job,
        "build_tutorial_steps",
        lambda segments: [
            {
                "step": 1,
                "action": "run_command",
                "instruction": "Install dependencies.",
                "start_time": 0.0,
                "end_time": 1.0,
                "evidence": {"source": "transcript", "text": "Run npm install."},
            }
        ],
    )

    # Invoke the FastAPI startup hook to model the next process starting.
    from app import main

    async def simulate_restart():
        await main.recover_interrupted_video_analyses()
        await main.app.state.analysis_recovery_task

    asyncio.run(simulate_restart())
    assert lifecycle == [
        "transcribe", "whisper_released", "visual_analysis"
    ]
    assert Path(video_path).is_file()
    assert not (storage.frames_dir / "4").exists()

    db = recovery_db()
    try:
        assert db.query(Video).filter(Video.id == 4).one().status == "completed"
    finally:
        db.close()

    # A second run uses the same storage functions as recovery and must replace,
    # not duplicate, each persisted result type.
    awaitable = run_in_threadpool(analysis_job.run_analysis_job, 4)
    asyncio.run(awaitable)
    assert lifecycle == [
        "transcribe", "whisper_released", "visual_analysis",
        "transcribe", "whisper_released", "visual_analysis",
    ]
    assert Path(video_path).is_file()
    assert not (storage.frames_dir / "4").exists()

    db = recovery_db()
    try:
        assert db.query(Video).filter(Video.id == 4).one().status == "completed"
        assert db.query(TranscriptSegment).filter(TranscriptSegment.video_id == 4).count() == 1
        assert db.query(Detection).filter(Detection.video_id == 4).count() == 1
        assert db.query(VideoEvidence).filter(VideoEvidence.video_id == 4).count() == 1
        assert db.query(TutorialStep).filter(TutorialStep.video_id == 4).count() == 1
    finally:
        db.close()


def test_visual_failure_cleans_frames_but_retains_source(
    recovery_db,
    monkeypatch,
    tmp_path,
):
    storage = LocalStorageBackend(tmp_path / "uploads", tmp_path / "frames")
    video_path = storage.save_stream(
        BytesIO(b"synthetic source"),
        make_video_storage_key("visual-failure", ".mp4"),
    )
    _add_video(
        recovery_db,
        video_id=45,
        status="processing",
        source_type="upload",
        filepath=video_path,
    )
    monkeypatch.setattr(analysis_job, "SessionLocal", recovery_db)
    monkeypatch.setattr(analysis_job, "get_local_storage", lambda: storage)
    monkeypatch.setattr(
        analysis_job,
        "transcribe_video",
        lambda path, *, max_duration, video_duration: {"segments": []},
    )
    monkeypatch.setattr(analysis_job, "release_transcription_model", lambda: None)

    def fail_visual_analysis(video_path, video_id, db, **kwargs):
        frame = Path(kwargs["frames_root"]) / str(video_id) / "partial.jpg"
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame.write_bytes(b"partial output")
        raise RuntimeError("synthetic visual failure")

    monkeypatch.setattr(analysis_job, "analyze_video", fail_visual_analysis)

    analysis_job.run_analysis_job(45)

    db = recovery_db()
    try:
        assert db.query(Video).filter(Video.id == 45).one().status == "failed"
    finally:
        db.close()

    assert Path(video_path).is_file()
    assert not (storage.frames_dir / "45").exists()
