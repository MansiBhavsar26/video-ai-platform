import pytest

from app.services.evidence_fusion import fuse_evidence


@pytest.fixture
def base_action():
    return {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "operation": "run",
        "start_time": 100.0,
        "end_time": 105.0,
        "confidence": 0.95,
    }


def test_empty_developer_actions_returns_empty_list():
    result = fuse_evidence(
        transcript_segments=[{"start_time": 100.0, "end_time": 101.0, "text": "I am going to install react-router-dom"}],
        ocr_results=[{"timestamp": 101.0, "text": "npm install react-router-dom", "evidence_type": "terminal"}],
        developer_actions=[],
        visual_events=[{"timestamp": 101.0, "label": "terminal"}],
    )

    assert result == []


def test_developer_action_alone_returns_event(base_action):
    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=[],
        developer_actions=[base_action],
        visual_events=[],
    )

    assert len(result) == 1
    event = result[0]
    assert event["event_type"] == "DEVELOPER_ACTION"
    assert event["action"] == "run_command"
    assert event["value"] == "npm install react-router-dom"
    assert event["operation"] == "run"
    assert event["timestamp"] == 100.0
    assert event["confidence"] == 0.95
    assert event["evidence"]["transcript"] == []
    assert event["evidence"]["ocr"] == []
    assert event["evidence"]["visual"] == []


def test_compact_visual_event_preserves_fused_evidence(base_action):
    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=[],
        developer_actions=[base_action],
        visual_events=[(101.0, "laptop")],
    )

    assert result[0]["evidence"]["visual"] == [
        {"timestamp": 101.0, "label": "laptop"}
    ]
    assert result[0]["confidence"] == 0.98


def test_matching_transcript_increases_confidence_and_adds_reason(base_action):
    transcript_segments = [
        {"start_time": 99.0, "end_time": 103.0, "text": "I am going to install react-router-dom"}
    ]

    result = fuse_evidence(
        transcript_segments=transcript_segments,
        ocr_results=[],
        developer_actions=[base_action],
        visual_events=[],
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["transcript"]
    assert event["confidence"] == 1.0
    assert "matching_transcript" in event["confidence_reasons"]


def test_matching_ocr_increases_confidence_and_adds_reason(base_action):
    ocr_results = [
        {"timestamp": 101.0, "text": "npm install react-router-dom", "evidence_type": "terminal"}
    ]

    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=ocr_results,
        developer_actions=[base_action],
        visual_events=[],
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["ocr"]
    assert event["confidence"] == 1.0
    assert "matching_ocr" in event["confidence_reasons"]


def test_unrelated_ocr_is_not_attached(base_action):
    ocr_results = [
        {"timestamp": 101.0, "text": "welcome to this tutorial", "evidence_type": "terminal"}
    ]

    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=ocr_results,
        developer_actions=[base_action],
        visual_events=[],
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["ocr"] == []
    assert event["confidence"] == 0.95
    assert "matching_ocr" not in event["confidence_reasons"]


def test_generic_ocr_single_token_is_not_attached(base_action):
    ocr_results = [{"timestamp": 101.0, "text": "install", "evidence_type": "terminal"}]

    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=ocr_results,
        developer_actions=[base_action],
        visual_events=[],
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["ocr"] == []
    assert event["confidence"] == 0.95


def test_compatible_visual_evidence_increases_confidence(base_action):
    visual_events = [{"timestamp": 101.0, "label": "terminal"}]

    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=[],
        developer_actions=[base_action],
        visual_events=visual_events,
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["visual"]
    assert event["confidence"] == 0.98
    assert "compatible_visual" in event["confidence_reasons"]


def test_unrelated_visual_evidence_is_not_attached(base_action):
    visual_events = [{"timestamp": 101.0, "label": "car"}]

    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=[],
        developer_actions=[base_action],
        visual_events=visual_events,
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["visual"] == []
    assert event["confidence"] == 0.95
    assert "compatible_visual" not in event["confidence_reasons"]


def test_all_evidence_together_clips_confidence_to_one(base_action):
    transcript_segments = [
        {"start_time": 99.0, "end_time": 103.0, "text": "I am going to install react-router-dom"}
    ]
    ocr_results = [
        {"timestamp": 101.0, "text": "npm install react-router-dom", "evidence_type": "terminal"}
    ]
    visual_events = [{"timestamp": 101.0, "label": "terminal"}]

    result = fuse_evidence(
        transcript_segments=transcript_segments,
        ocr_results=ocr_results,
        developer_actions=[{**base_action, "confidence": 0.90}],
        visual_events=visual_events,
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["transcript"]
    assert event["evidence"]["ocr"]
    assert event["evidence"]["visual"]
    assert event["confidence"] == 1.0
    assert "matching_transcript" in event["confidence_reasons"]
    assert "matching_ocr" in event["confidence_reasons"]
    assert "compatible_visual" in event["confidence_reasons"]


def test_duplicate_evidence_is_removed():
    developer_action = {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "operation": "run",
        "start_time": 100.0,
        "end_time": 105.0,
        "confidence": 0.90,
    }

    transcript_segments = [
        {"start_time": 99.0, "end_time": 103.0, "text": "I am going to install react-router-dom"},
        {"start_time": 99.0, "end_time": 103.0, "text": "I am going to install react-router-dom"},
    ]
    ocr_results = [
        {"timestamp": 101.0, "text": "npm install react-router-dom", "evidence_type": "terminal"},
        {"timestamp": 101.0, "text": "npm install react-router-dom", "evidence_type": "terminal"},
    ]
    visual_events = [
        {"timestamp": 101.0, "label": "terminal"},
        {"timestamp": 101.0, "label": "terminal"},
    ]

    result = fuse_evidence(
        transcript_segments=transcript_segments,
        ocr_results=ocr_results,
        developer_actions=[developer_action],
        visual_events=visual_events,
    )

    assert len(result) == 1
    event = result[0]
    assert len(event["evidence"]["transcript"]) == 1
    assert len(event["evidence"]["ocr"]) == 1
    assert len(event["evidence"]["visual"]) == 1


def test_malformed_timestamps_do_not_crash_and_are_deterministic():
    developer_action = {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "operation": "run",
        "start_time": 100.0,
        "end_time": 105.0,
        "confidence": 0.90,
    }

    result = fuse_evidence(
        transcript_segments=[
            {"start_time": "not-a-number", "end_time": None, "text": "install react-router-dom"},
            {"start_time": None, "end_time": 105.0, "text": "npm install react-router-dom"},
        ],
        ocr_results=[
            {"timestamp": "not-a-number", "text": "npm install react-router-dom", "evidence_type": "terminal"},
            {"timestamp": None, "text": "npm install react-router-dom", "evidence_type": "terminal"},
        ],
        developer_actions=[developer_action],
        visual_events=[
            {"timestamp": "not-a-number", "label": "terminal"},
            {"timestamp": None, "label": "terminal"},
        ],
    )

    assert len(result) == 1
    event = result[0]
    assert event["event_type"] == "DEVELOPER_ACTION"
    assert event["confidence"] >= 0.0


def test_chronological_order_is_sorted_by_timestamp():
    developer_actions = [
        {"action": "run_command", "value": "first", "operation": "run", "start_time": 200.0, "end_time": 205.0, "confidence": 1.0},
        {"action": "run_command", "value": "second", "operation": "run", "start_time": 100.0, "end_time": 105.0, "confidence": 1.0},
        {"action": "run_command", "value": "third", "operation": "run", "start_time": 150.0, "end_time": 155.0, "confidence": 1.0},
    ]

    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=[],
        developer_actions=developer_actions,
        visual_events=[],
    )

    assert [event["timestamp"] for event in result] == [100.0, 150.0, 200.0]


def test_confidence_upper_bound_clips_to_one():
    developer_action = {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "operation": "run",
        "start_time": 100.0,
        "end_time": 105.0,
        "confidence": 1.5,
    }

    result = fuse_evidence(
        transcript_segments=[{"start_time": 99.0, "end_time": 103.0, "text": "I am going to install react-router-dom"}],
        ocr_results=[{"timestamp": 101.0, "text": "npm install react-router-dom", "evidence_type": "terminal"}],
        developer_actions=[developer_action],
        visual_events=[{"timestamp": 101.0, "label": "terminal"}],
    )

    assert len(result) == 1
    assert result[0]["confidence"] == 1.0


def test_confidence_lower_bound_clips_to_zero():
    developer_action = {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "operation": "run",
        "start_time": 100.0,
        "end_time": 105.0,
        "confidence": -0.5,
    }

    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=[],
        developer_actions=[developer_action],
        visual_events=[],
    )

    assert len(result) == 1
    assert result[0]["confidence"] == 0.0


def test_temporal_window_rejects_far_evidence(base_action):
    transcript_segments = [{"start_time": 110.0, "end_time": 112.0, "text": "I am going to install react-router-dom"}]
    ocr_results = [{"timestamp": 110.0, "text": "npm install react-router-dom", "evidence_type": "terminal"}]
    visual_events = [{"timestamp": 110.0, "label": "terminal"}]

    result = fuse_evidence(
        transcript_segments=transcript_segments,
        ocr_results=ocr_results,
        developer_actions=[base_action],
        visual_events=visual_events,
        time_window_seconds=3.0,
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["transcript"] == []
    assert event["evidence"]["ocr"] == []
    assert event["evidence"]["visual"] == []
    assert event["confidence"] == 0.95
    assert "matching_transcript" not in event["confidence_reasons"]
    assert "matching_ocr" not in event["confidence_reasons"]
    assert "compatible_visual" not in event["confidence_reasons"]


def test_overlapping_time_range_accepts_evidence_within_range():
    developer_action = {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "operation": "run",
        "start_time": 100.0,
        "end_time": 110.0,
        "confidence": 0.90,
    }
    transcript_segments = [
        {"start_time": 105.0, "end_time": 108.0, "text": "I am going to install react-router-dom"}
    ]

    result = fuse_evidence(
        transcript_segments=transcript_segments,
        ocr_results=[],
        developer_actions=[developer_action],
        visual_events=[],
    )

    assert len(result) == 1
    event = result[0]
    assert event["evidence"]["transcript"]


def test_fused_event_contains_required_structure():
    developer_action = {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "operation": "run",
        "start_time": 100.0,
        "end_time": 105.0,
        "confidence": 0.90,
        "evidence": {"source": "developer"},
    }

    result = fuse_evidence(
        transcript_segments=[{"start_time": 99.0, "end_time": 103.0, "text": "I am going to install react-router-dom"}],
        ocr_results=[{"timestamp": 101.0, "text": "npm install react-router-dom", "evidence_type": "terminal"}],
        developer_actions=[developer_action],
        visual_events=[{"timestamp": 101.0, "label": "terminal"}],
    )

    assert len(result) == 1
    event = result[0]
    required_fields = {
        "timestamp",
        "event_type",
        "action",
        "value",
        "operation",
        "confidence",
        "evidence",
        "confidence_reasons",
    }
    assert required_fields.issubset(event.keys())
    assert set(event["evidence"].keys()) == {"transcript", "ocr", "developer_action", "visual"}


def test_developer_action_data_is_preserved_in_evidence_snapshot():
    developer_action = {
        "action": "run_command",
        "value": "npm install react-router-dom",
        "operation": "run",
        "start_time": 100.0,
        "end_time": 105.0,
        "confidence": 0.90,
        "evidence": {"source": "manual"},
    }

    result = fuse_evidence(
        transcript_segments=[],
        ocr_results=[],
        developer_actions=[developer_action],
        visual_events=[],
    )

    assert len(result) == 1
    captured = result[0]["evidence"]["developer_action"]
    assert captured["action"] == "run_command"
    assert captured["value"] == "npm install react-router-dom"
    assert captured["operation"] == "run"
    assert captured["start_time"] == 100.0
    assert captured["end_time"] == 105.0
    assert captured["confidence"] == 0.90
    assert captured["evidence"] == {"source": "manual"}
