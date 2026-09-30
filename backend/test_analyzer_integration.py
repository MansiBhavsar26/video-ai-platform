from app.services import analyzer


class DummyDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass


def test_analyze_video_includes_developer_actions_and_fused_evidence(monkeypatch):
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
        lambda filepath: "npm install react",
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
        "aggregate_detections",
        lambda detections: {"laptop": 1},
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
        {"timestamp": 1.0, "label": "laptop"}
    ]
    assert captured["time_window_seconds"] == 3.0

    assert result["frames_processed"] == 1
    assert result["detections_created"] == 1
    assert result["developer_actions"] == developer_actions
    assert result["fused_evidence"] == fused_evidence
    assert result["ocr_results"][0]["text"] == "npm install react"
    assert result["object_summary"] == {"laptop": 1}
    assert result["timeline"] == [{"timestamp": 1.0}]
    assert result["scene_changes"] == []
    assert result["description"] == "description"
    assert detector_releases == [True]
