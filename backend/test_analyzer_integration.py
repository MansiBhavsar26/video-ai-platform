import pytest

from app.services import analyzer
from app.services.developer_action_pipeline import build_tutorial_steps


class DummyDB:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1

    def commit(self):
        pass


def test_analyze_video_includes_developer_actions_and_fused_evidence(monkeypatch):
    monkeypatch.setattr(analyzer, "ENABLE_OBJECT_DETECTION", True)
    frames = [
        {
            "filepath": "frame_1.jpg",
            "timestamp": 1.0,
        }
    ]

    transcript_segments = [
        {
            "start_time": 0.0,
            "end_time": 2.0,
            "text": "npm install react",
        }
    ]

    developer_actions = [
        {
            "action": "run_command",
            "start_time": 1.0,
            "end_time": 2.0,
            "confidence": 0.7,
        }
    ]

    fused_evidence = [
        {
            "timestamp": 1.0,
            "event_type": "DEVELOPER_ACTION",
        }
    ]

    captured = {}
    detector_releases = []

    def fake_build_developer_action_timeline(segments):
        captured["segments"] = segments
        return developer_actions

    def fake_fuse_evidence(
        transcript_segments,
        ocr_results,
        developer_actions,
        visual_events,
        time_window_seconds,
    ):
        captured["transcript_segments"] = transcript_segments
        captured["developer_actions"] = developer_actions
        captured["visual_events"] = visual_events
        captured["time_window_seconds"] = time_window_seconds
        return fused_evidence

    monkeypatch.setattr(
        analyzer,
        "smart_sample_video",
        lambda video_path, output_dir: frames,
    )
    monkeypatch.setattr(
        analyzer,
        "release_detector_model",
        lambda: detector_releases.append(True),
    )
    monkeypatch.setattr(
        analyzer,
        "detect_objects",
        lambda filepath: [
            {
                "label": "laptop",
                "confidence": 0.92,
                "x1": 10,
                "y1": 20,
                "x2": 110,
                "y2": 120,
            }
        ],
    )
    monkeypatch.setattr(
        analyzer,
        "extract_text",
        lambda filepath, video_id=None: "npm install react",
    )
    monkeypatch.setattr(
        analyzer,
        "clean_ocr_text",
        lambda raw: "npm install react",
    )
    monkeypatch.setattr(
        analyzer,
        "classify_evidence",
        lambda text: "command",
    )
    monkeypatch.setattr(
        analyzer,
        "get_evidence_confidence",
        lambda evidence_type: 0.8,
    )
    monkeypatch.setattr(
        analyzer,
        "detect_scene_changes",
        lambda frames: [],
    )
    monkeypatch.setattr(
        analyzer,
        "build_timeline",
        lambda object_summary, ocr_results, scene_changes: [{"timestamp": 1.0}],
    )
    monkeypatch.setattr(
        analyzer,
        "save_video_evidence",
        lambda db, video_id, evidence: None,
    )
    monkeypatch.setattr(
        analyzer,
        "generate_video_description",
        lambda frames, detections, video_duration, ocr_results: "description",
    )
    monkeypatch.setattr(
        analyzer,
        "build_developer_action_timeline",
        fake_build_developer_action_timeline,
    )
    monkeypatch.setattr(
        analyzer,
        "fuse_evidence",
        fake_fuse_evidence,
    )

    db = DummyDB()
    result = analyzer.analyze_video(
        video_path="sample.mp4",
        video_id=42,
        db=db,
        video_duration=12.5,
        transcript_segments=transcript_segments,
    )

    assert captured["segments"] == transcript_segments
    assert captured["transcript_segments"] == transcript_segments
    assert captured["developer_actions"] == developer_actions
    assert captured["visual_events"] == [
        (1.0, "laptop")
    ]
    assert captured["time_window_seconds"] == 3.0

    assert result["frames_processed"] == 1
    assert result["detections_created"] == 1
    assert result["developer_actions"] == developer_actions
    assert result["fused_evidence"] == fused_evidence
    assert result["ocr_results"][0]["text"] == "npm install react"
    assert result["object_summary"] == [
        {
            "label": "laptop",
            "appearances": 1,
            "first_seen": 1.0,
            "last_seen": 1.0,
            "average_confidence": 0.92,
        }
    ]
    assert result["timeline"] == [{"timestamp": 1.0}]
    assert result["scene_changes"] == []
    assert result["description"] == "description"
    assert detector_releases == [True]
    assert db.flush_count == 1


def test_disabled_detection_keeps_ocr_evidence_and_tutorial_steps(monkeypatch, caplog):
    caplog.set_level("INFO")
    frames = [
        {"filepath": f"frame_{index}.jpg", "timestamp": float(index)}
        for index in range(4)
    ]
    transcript_segments = [
        {
            "start_time": 0.0,
            "end_time": 2.0,
            "text": "Now let's create our Product Item component",
        }
    ]
    ocr_frames = []
    saved_evidence = []

    monkeypatch.setattr(analyzer, "ENABLE_OBJECT_DETECTION", False)
    monkeypatch.setattr(analyzer, "smart_sample_video", lambda **kwargs: frames)
    monkeypatch.setattr(
        analyzer,
        "detect_objects",
        lambda *args, **kwargs: pytest.fail("detector ran while disabled"),
    )
    monkeypatch.setattr(
        analyzer,
        "release_detector_model",
        lambda: pytest.fail("detector model was loaded while disabled"),
    )

    def extract_text(path, video_id=None):
        ocr_frames.append(path)
        return "npm install react"

    monkeypatch.setattr(analyzer, "extract_text", extract_text)
    monkeypatch.setattr(analyzer, "detect_scene_changes", lambda frames: [])
    monkeypatch.setattr(
        analyzer,
        "save_video_evidence",
        lambda db, video_id, evidence: saved_evidence.extend(evidence),
    )
    monkeypatch.setattr(
        analyzer,
        "generate_video_description",
        lambda **kwargs: "description without object detections",
    )

    result = analyzer.analyze_video(
        video_path="sample.mp4",
        video_id=43,
        db=DummyDB(),
        video_duration=4.0,
        transcript_segments=transcript_segments,
    )
    steps = build_tutorial_steps(transcript_segments)

    assert "video=43 object_detection disabled" in caplog.text
    assert "video=43 stage=ocr start" in caplog.text
    assert "video=43 stage=evidence complete" in caplog.text
    assert result["detections_created"] == 0
    assert ocr_frames == ["frame_0.jpg", "frame_3.jpg"]
    assert len(result["ocr_results"]) == 2
    assert len(saved_evidence) == 2
    assert result["developer_actions"]
    assert steps
    assert steps[0]["action"] == "create_component"
    assert {
        "step",
        "action",
        "name",
        "path",
        "instruction",
        "start_time",
        "end_time",
        "confidence",
        "evidence",
    }.issubset(steps[0])


def test_ocr_runs_periodically_and_on_detected_screen_frames():
    assert analyzer._should_run_ocr(0, [])
    assert not analyzer._should_run_ocr(1, [])
    assert not analyzer._should_run_ocr(2, [{"label": "person"}])
    assert analyzer._should_run_ocr(1, [{"label": "laptop"}])
    assert analyzer._should_run_ocr(2, [{"label": "TV"}])
    assert analyzer._should_run_ocr(2, [{"label": "cell phone"}])


def test_ocr_failure_degrades_without_interrupting_visual_analysis(monkeypatch):
    monkeypatch.setattr(
        analyzer,
        "extract_text",
        lambda frame_path, video_id=None: (_ for _ in ()).throw(FileNotFoundError("hidden path")),
    )

    assert analyzer._extract_ocr_text_safely("frame.jpg") == ""


def test_visual_analysis_completes_when_ocr_raises(monkeypatch):
    monkeypatch.setattr(
        analyzer,
        "smart_sample_video",
        lambda video_path, output_dir: [{"filepath": "frame.jpg", "timestamp": 1.0}],
    )
    monkeypatch.setattr(analyzer, "release_detector_model", lambda: None)
    monkeypatch.setattr(analyzer, "detect_objects", lambda filepath: [])
    monkeypatch.setattr(
        analyzer,
        "extract_text",
        lambda filepath, video_id=None: (_ for _ in ()).throw(FileNotFoundError("hidden path")),
    )
    monkeypatch.setattr(analyzer, "detect_scene_changes", lambda frames: [])
    monkeypatch.setattr(analyzer, "build_timeline", lambda *args: [])
    monkeypatch.setattr(analyzer, "save_video_evidence", lambda **kwargs: None)
    monkeypatch.setattr(analyzer, "generate_video_description", lambda **kwargs: "ok")
    monkeypatch.setattr(analyzer, "build_developer_action_timeline", lambda segments: [])
    monkeypatch.setattr(analyzer, "fuse_evidence", lambda **kwargs: [])

    result = analyzer.analyze_video(
        video_path="sample.mp4",
        video_id=7,
        db=DummyDB(),
        video_duration=2,
        transcript_segments=[],
    )

    assert result["description"] == "ok"
    assert result["ocr_results"] == []
