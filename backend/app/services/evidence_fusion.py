import re
from typing import Any

STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "this",
    "that",
    "then",
    "here",
    "it",
    "is",
    "are",
    "was",
    "were",
    "from",
    "into",
    "at",
    "by",
    "be",
    "do",
    "does",
    "did",
    "new",
    "named",
    "called",
    "using",
    "out",
}

GENERIC_TOKENS = {
    "install",
    "run",
    "start",
    "open",
    "edit",
    "update",
    "create",
    "delete",
    "save",
    "view",
    "show",
    "file",
    "folder",
    "project",
    "command",
    "terminal",
    "screen",
    "monitor",
    "laptop",
    "keyboard",
    "computer",
    "code",
    "app",
    "tool",
    "use",
    "using",
    "select",
    "build",
}

VISUAL_COMPATIBILITY = {
    "run_command": {
        "terminal",
        "laptop",
        "keyboard",
        "computer",
        "screen",
        "monitor",
        "tv",
    },
    "create_file": {
        "laptop",
        "keyboard",
        "computer",
        "screen",
        "monitor",
    },
    "edit_file": {
        "laptop",
        "keyboard",
        "computer",
        "screen",
        "monitor",
    },
    "open_file": {
        "laptop",
        "keyboard",
        "computer",
        "screen",
        "monitor",
    },
    "navigate_file": {
        "laptop",
        "keyboard",
        "computer",
        "screen",
        "monitor",
    },
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _meaningful_tokens(value: Any) -> list[str]:
    text = _normalize_text(value)
    if not text:
        return []

    return [
        token
        for token in text.split()
        if len(token) > 1 and token not in STOP_WORDS
    ]


def _token_overlap_score(left: Any, right: Any) -> float:
    left_tokens = _meaningful_tokens(left)
    right_tokens = _meaningful_tokens(right)

    if not left_tokens or not right_tokens:
        return 0.0

    left_set = set(left_tokens)
    right_set = set(right_tokens)
    normalized_left = _normalize_text(left)
    normalized_right = _normalize_text(right)

    if normalized_left and normalized_left == normalized_right:
        return 1.0

    overlap = left_set & right_set
    if not overlap:
        return 0.0

    score = (2.0 * len(overlap)) / (len(left_set) + len(right_set))
    return round(score, 3)


def _is_generic_only_text(value: Any) -> bool:
    tokens = _meaningful_tokens(value)
    return len(tokens) == 1 and tokens[0] in GENERIC_TOKENS


def _is_textually_compatible(action: dict, candidate_text: Any) -> bool:
    if not isinstance(action, dict):
        return False

    action_text = " ".join(
        str(part)
        for part in (
            action.get("action"),
            action.get("value"),
            action.get("operation"),
            action.get("evidence"),
        )
        if part is not None
    )
    if not action_text or not candidate_text:
        return False

    action_norm = _normalize_text(action_text)
    candidate_norm = _normalize_text(candidate_text)

    if action_norm and action_norm == candidate_norm:
        return True

    action_tokens = _meaningful_tokens(action_text)
    candidate_tokens = _meaningful_tokens(candidate_text)

    if not action_tokens or not candidate_tokens:
        return False

    if _is_generic_only_text(action_text) or _is_generic_only_text(candidate_text):
        return False

    score = _token_overlap_score(action_text, candidate_text)
    if score >= 0.75:
        return True

    if score >= 0.6 and len(action_tokens) > 1 and len(candidate_tokens) > 1:
        return True

    return False


def _compatible_visual_event(action: dict, visual_event: dict) -> bool:
    if not isinstance(action, dict):
        return False

    action_type = (action.get("action") or "").strip().lower().replace(" ", "_")
    if isinstance(visual_event, tuple) and len(visual_event) == 2:
        label_text = str(visual_event[1])
    elif isinstance(visual_event, dict):
        label_text = " ".join(
            str(part)
            for part in (visual_event.get("label"), visual_event.get("event_type"))
            if part is not None
        )
    else:
        return False
    if not action_type or not label_text:
        return False

    compatible_labels = VISUAL_COMPATIBILITY.get(action_type, set())
    if not compatible_labels:
        return False

    labels = set(_meaningful_tokens(label_text))
    if not labels:
        return False

    return bool(labels & compatible_labels)


def _deduplicate(items: list[dict]) -> list[dict]:
    seen = set()
    unique_items: list[dict] = []

    for item in items:
        marker = (
            item.get("start_time"),
            item.get("end_time"),
            item.get("text"),
            item.get("timestamp"),
            item.get("label"),
        )
        if marker in seen:
            continue
        seen.add(marker)
        unique_items.append(item)

    return unique_items


def _is_temporally_close(
    start_time: float,
    end_time: float,
    target_start: float,
    target_end: float,
    window_seconds: float,
) -> bool:
    if start_time > end_time:
        start_time, end_time = end_time, start_time

    if target_start > target_end:
        target_start, target_end = target_end, target_start

    overlap = max(0.0, min(end_time, target_end) - max(start_time, target_start))
    if overlap > 0:
        return True

    nearest_distance = min(
        abs(start_time - target_end),
        abs(end_time - target_start),
        abs(start_time - target_start),
        abs(end_time - target_end),
    )

    return nearest_distance <= window_seconds


def fuse_evidence(
    transcript_segments,
    ocr_results,
    developer_actions,
    visual_events=None,
    time_window_seconds=3.0,
) -> list[dict]:
    """Fuse transcript, OCR, developer actions, and visual events into developer-action-centric evidence events."""

    if visual_events is None:
        visual_events = []

    if not developer_actions:
        return []

    events: list[dict] = []
    time_window = max(float(time_window_seconds), 0.0)

    for action in developer_actions:
        if not isinstance(action, dict):
            continue

        action_start = _safe_float(action.get("start_time"), 0.0)
        action_end = _safe_float(action.get("end_time"), action_start)
        action_confidence = min(max(_safe_float(action.get("confidence"), 0.0), 0.0), 1.0)

        transcript_matches: list[dict] = []
        for segment in transcript_segments or []:
            if not isinstance(segment, dict):
                continue

            segment_start = _safe_float(segment.get("start_time"), 0.0)
            segment_end = _safe_float(segment.get("end_time"), segment_start)
            segment_text = segment.get("text") or ""

            if not _is_temporally_close(
                segment_start,
                segment_end,
                action_start,
                action_end,
                time_window,
            ):
                continue

            if not _is_textually_compatible(action, segment_text):
                continue

            transcript_matches.append(segment)

        ocr_matches: list[dict] = []
        for result in ocr_results or []:
            if not isinstance(result, dict):
                continue

            timestamp = _safe_float(result.get("timestamp"), 0.0)
            if abs(timestamp - action_start) > time_window and not (
                action_start <= timestamp <= action_end or action_start - time_window <= timestamp <= action_end + time_window
            ):
                continue

            text = result.get("text") or ""
            if not _is_textually_compatible(action, text):
                continue

            ocr_matches.append(result)

        visual_matches: list[dict] = []
        for event in visual_events or []:
            if isinstance(event, tuple) and len(event) == 2:
                event_timestamp, event_label = event
                event = {"timestamp": event_timestamp, "label": event_label}
            if not isinstance(event, dict):
                continue

            event_timestamp = _safe_float(event.get("timestamp"), 0.0)
            if abs(event_timestamp - action_start) > time_window and not (
                action_start <= event_timestamp <= action_end or action_start - time_window <= event_timestamp <= action_end + time_window
            ):
                continue

            if not _compatible_visual_event(action, event):
                continue

            visual_matches.append(event)

        transcript_matches = _deduplicate(transcript_matches)
        ocr_matches = _deduplicate(ocr_matches)
        visual_matches = _deduplicate(visual_matches)

        confidence = action_confidence
        reasons: list[str] = ["developer_action_confidence"]

        if transcript_matches:
            confidence = min(1.0, confidence + 0.05)
            reasons.append("matching_transcript")

        if ocr_matches:
            confidence = min(1.0, confidence + 0.05)
            reasons.append("matching_ocr")

        if visual_matches:
            confidence = min(1.0, confidence + 0.03)
            reasons.append("compatible_visual")

        timestamp = action_start if action_start else (
            (action_end + action_start) / 2.0 if action_end else 0.0
        )

        event = {
            "timestamp": timestamp,
            "event_type": "DEVELOPER_ACTION",
            "action": action.get("action"),
            "value": action.get("value"),
            "operation": action.get("operation"),
            "confidence": round(confidence, 3),
            "evidence": {
                "transcript": transcript_matches,
                "ocr": ocr_matches,
                "developer_action": {
                    "action": action.get("action"),
                    "value": action.get("value"),
                    "operation": action.get("operation"),
                    "start_time": _safe_float(action.get("start_time"), 0.0),
                    "end_time": _safe_float(action.get("end_time"), 0.0),
                    "confidence": action_confidence,
                    "evidence": action.get("evidence"),
                },
                "visual": visual_matches,
            },
            "confidence_reasons": reasons,
        }

        events.append(event)

    events.sort(key=lambda item: _safe_float(item.get("timestamp"), 0.0))
    return events
