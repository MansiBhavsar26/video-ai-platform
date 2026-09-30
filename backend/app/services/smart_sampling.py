import os
import shutil
from typing import Any

import cv2

from app.config import (
    SMART_SAMPLING_COARSE_INTERVAL,
    SMART_SAMPLING_ENABLED,
    SMART_SAMPLING_MIN_FRAME_GAP,
    SMART_SAMPLING_REFINEMENT_INTERVAL,
    SMART_SAMPLING_REFINEMENT_WINDOW,
    SMART_SAMPLING_VISUAL_THRESHOLD,
    VIDEO_ANALYSIS_FRAME_ANALYSIS_INTERVAL_SECONDS,
    VIDEO_ANALYSIS_MAX_FRAMES,
)

from .video_processor import extract_frames, write_analysis_frame


def _normalize_frames(
    frames: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return filepath/timestamp records in chronological order with duplicates removed."""

    if not frames:
        return []

    normalized: dict[float, dict[str, Any]] = {}

    for frame in frames:
        if not isinstance(frame, dict):
            continue

        filepath = frame.get("filepath")
        timestamp = frame.get("timestamp")

        if filepath is None or timestamp is None:
            continue

        rounded_timestamp = round(float(timestamp), 6)
        normalized.setdefault(
            rounded_timestamp,
            {
                "filepath": filepath,
                "timestamp": float(timestamp),
            },
        )

    return sorted(
        normalized.values(),
        key=lambda item: item["timestamp"],
    )


def _apply_min_frame_gap(
    frames: list[dict[str, Any]],
    min_frame_gap_seconds: float,
) -> list[dict[str, Any]]:
    """Keep a sparse, chronological frame set while respecting the minimum time gap."""

    if not frames:
        return []

    min_gap = max(float(min_frame_gap_seconds), 0.0)
    selected: list[dict[str, Any]] = []

    for frame in frames:
        current_timestamp = float(frame["timestamp"])

        if not selected:
            selected.append(frame)
            continue

        previous_timestamp = float(selected[-1]["timestamp"])

        if current_timestamp - previous_timestamp >= min_gap:
            selected.append(frame)

    return selected


def _visual_change_score(
    frame_a_path: str,
    frame_b_path: str,
    comparison_size: tuple[int, int] = (32, 32),
) -> float:
    """Measure the visual difference between two small grayscale frames."""

    if not frame_a_path or not frame_b_path:
        return 0.0

    first_image = cv2.imread(frame_a_path, cv2.IMREAD_GRAYSCALE)
    second_image = cv2.imread(frame_b_path, cv2.IMREAD_GRAYSCALE)

    if first_image is None or second_image is None:
        return 0.0

    first_image = cv2.resize(
        first_image,
        comparison_size,
        interpolation=cv2.INTER_AREA,
    )
    second_image = cv2.resize(
        second_image,
        comparison_size,
        interpolation=cv2.INTER_AREA,
    )

    diff = cv2.absdiff(first_image, second_image)
    return float(diff.mean())


def _detect_change_timestamps(
    frames: list[dict[str, Any]],
    threshold: float,
) -> list[float]:
    """Find neighboring coarse frames that differ beyond a lightweight threshold."""

    normalized = _normalize_frames(frames)

    if len(normalized) < 2:
        return []

    change_timestamps: list[float] = []
    valid_comparison_count = 0

    for index in range(1, len(normalized)):
        previous_frame = normalized[index - 1]
        current_frame = normalized[index]

        if not os.path.exists(previous_frame["filepath"]) or not os.path.exists(current_frame["filepath"]):
            continue

        valid_comparison_count += 1
        score = _visual_change_score(
            previous_frame["filepath"],
            current_frame["filepath"],
        )

        if score >= threshold:
            change_timestamps.append(float(current_frame["timestamp"]))

    if valid_comparison_count == 0:
        return []

    return change_timestamps


def _extract_window_frames(
    video_path: str,
    output_dir: str,
    start_time: float,
    end_time: float,
    interval_seconds: float,
    max_frames: int | None = None,
) -> list[dict[str, Any]]:
    """Sample a time window using the same seek-based mechanism as the base extractor."""

    if end_time < start_time:
        return []

    interval_seconds = max(float(interval_seconds), 0.1)
    os.makedirs(output_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        cap.release()
        raise ValueError("Could not open video")

    window_frames: list[dict[str, Any]] = []

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0:
            raise ValueError("Could not determine video FPS")

        duration = frame_count / fps if frame_count > 0 else 0.0
        if duration <= 0:
            return []

        if max_frames is not None and max_frames > 0:
            interval_seconds = max(
                interval_seconds,
                max((float(end_time) - float(start_time)), 0.0) / max_frames,
            )

        timestamp = max(0.0, float(start_time))
        while timestamp <= float(end_time) and (
            max_frames is None or len(window_frames) < max_frames
        ):
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
            success, frame = cap.read()

            if success:
                actual_frame_index = cap.get(cv2.CAP_PROP_POS_FRAMES) - 1
                actual_timestamp = actual_frame_index / fps

                if actual_timestamp < start_time:
                    del frame
                    timestamp += interval_seconds
                    continue

                if actual_timestamp > end_time:
                    del frame
                    break

                filepath = os.path.join(
                    output_dir,
                    f"frame_{actual_timestamp:.3f}.jpg",
                )
                write_analysis_frame(frame, filepath)
                window_frames.append(
                    {
                        "filepath": filepath,
                        "timestamp": float(actual_timestamp),
                    }
                )
                del frame

            timestamp += interval_seconds

        return _normalize_frames(window_frames)
    finally:
        cap.release()


def smart_sample_frames(
    frames: list[dict[str, Any]],
    coarse_interval_seconds: float = SMART_SAMPLING_COARSE_INTERVAL,
    visual_change_threshold: float = SMART_SAMPLING_VISUAL_THRESHOLD,
    refinement_window_seconds: float = SMART_SAMPLING_REFINEMENT_WINDOW,
    refinement_interval_seconds: float = SMART_SAMPLING_REFINEMENT_INTERVAL,
    min_frame_gap_seconds: float = SMART_SAMPLING_MIN_FRAME_GAP,
) -> list[dict[str, Any]]:
    """Select a sparse, representative frame set with denser refinement around visual changes."""

    normalized = _normalize_frames(frames)

    if not normalized:
        return []

    if len(normalized) == 1:
        return [
            {
                "filepath": normalized[0]["filepath"],
                "timestamp": normalized[0]["timestamp"],
            }
        ]

    selected: dict[float, dict[str, Any]] = {
        float(normalized[0]["timestamp"]): {
            "filepath": normalized[0]["filepath"],
            "timestamp": float(normalized[0]["timestamp"]),
        },
        float(normalized[-1]["timestamp"]): {
            "filepath": normalized[-1]["filepath"],
            "timestamp": float(normalized[-1]["timestamp"]),
        },
    }

    change_timestamps = _detect_change_timestamps(
        normalized,
        threshold=visual_change_threshold,
    )

    if not change_timestamps:
        for frame in normalized:
            selected[float(frame["timestamp"])] = {
                "filepath": frame["filepath"],
                "timestamp": float(frame["timestamp"]),
            }

        result = _apply_min_frame_gap(
            sorted(selected.values(), key=lambda item: item["timestamp"]),
            min_frame_gap_seconds,
        )
        return result

    for change_timestamp in change_timestamps:
        start_time = max(0.0, change_timestamp - refinement_window_seconds)
        end_time = change_timestamp + refinement_window_seconds

        for frame in normalized:
            candidate_timestamp = float(frame["timestamp"])
            if start_time <= candidate_timestamp <= end_time:
                selected[candidate_timestamp] = {
                    "filepath": frame["filepath"],
                    "timestamp": candidate_timestamp,
                }

    result = _apply_min_frame_gap(
        sorted(selected.values(), key=lambda item: item["timestamp"]),
        min_frame_gap_seconds,
    )
    return result


def smart_sample_video(
    video_path: str,
    output_dir: str,
    coarse_interval_seconds: float = SMART_SAMPLING_COARSE_INTERVAL,
    visual_change_threshold: float = SMART_SAMPLING_VISUAL_THRESHOLD,
    refinement_window_seconds: float = SMART_SAMPLING_REFINEMENT_WINDOW,
    refinement_interval_seconds: float = SMART_SAMPLING_REFINEMENT_INTERVAL,
    min_frame_gap_seconds: float = SMART_SAMPLING_MIN_FRAME_GAP,
    enabled: bool = SMART_SAMPLING_ENABLED,
    max_frames: int = VIDEO_ANALYSIS_MAX_FRAMES,
    frame_analysis_interval_seconds: float = VIDEO_ANALYSIS_FRAME_ANALYSIS_INTERVAL_SECONDS,
) -> list[dict[str, Any]]:
    """Use a coarse-to-fine seek-based sampling strategy and keep every returned frame under output_dir."""

    os.makedirs(output_dir, exist_ok=True)
    max_frames = max(1, int(max_frames))
    coarse_interval_seconds = max(
        float(coarse_interval_seconds),
        float(frame_analysis_interval_seconds),
    )
    min_frame_gap_seconds = max(
        float(min_frame_gap_seconds),
        float(frame_analysis_interval_seconds),
    )

    if not enabled:
        return extract_frames(
            video_path=video_path,
            output_dir=output_dir,
            interval_seconds=coarse_interval_seconds,
            max_frames=max_frames,
        )

    smart_dir = os.path.join(output_dir, "smart")
    coarse_dir = os.path.join(smart_dir, "coarse")
    refined_dir = os.path.join(smart_dir, "refined")
    selected_dir = os.path.join(smart_dir, "selected")

    os.makedirs(coarse_dir, exist_ok=True)
    os.makedirs(refined_dir, exist_ok=True)
    os.makedirs(selected_dir, exist_ok=True)

    coarse_frames = extract_frames(
        video_path=video_path,
        output_dir=coarse_dir,
        interval_seconds=coarse_interval_seconds,
        max_frames=max_frames,
    )

    if not coarse_frames:
        return []

    selected_by_timestamp: dict[float, dict[str, Any]] = {
        float(frame["timestamp"]): {
            "filepath": frame["filepath"],
            "timestamp": float(frame["timestamp"]),
        }
        for frame in coarse_frames
    }

    change_timestamps = _detect_change_timestamps(
        coarse_frames,
        threshold=visual_change_threshold,
    )

    if change_timestamps:
        # Bound refinement work even when a long screen recording changes often.
        for change_timestamp in change_timestamps[:12]:
            window_start = max(0.0, change_timestamp - refinement_window_seconds)
            window_end = change_timestamp + refinement_window_seconds
            window_dir = os.path.join(
                refined_dir,
                f"refine_{int(change_timestamp * 1000)}",
            )

            refined_window = _extract_window_frames(
                video_path=video_path,
                output_dir=window_dir,
                start_time=window_start,
                end_time=window_end,
                interval_seconds=max(
                    refinement_interval_seconds,
                    frame_analysis_interval_seconds,
                ),
                max_frames=8,
            )

            for frame in refined_window:
                selected_by_timestamp[float(frame["timestamp"])] = {
                    "filepath": frame["filepath"],
                    "timestamp": float(frame["timestamp"]),
                }

    result = _apply_min_frame_gap(
        sorted(selected_by_timestamp.values(), key=lambda item: item["timestamp"]),
        min_frame_gap_seconds,
    )

    if len(result) > max_frames:
        if max_frames == 1:
            result = [result[0]]
        else:
            last_index = len(result) - 1
            result = [
                result[round(index * last_index / (max_frames - 1))]
                for index in range(max_frames)
            ]

    persistent_frames: list[dict[str, Any]] = []

    for frame in result:
        timestamp_text = f"{float(frame['timestamp']):.3f}"
        persistent_path = os.path.join(
            selected_dir,
            f"frame_{timestamp_text}.jpg",
        )

        if os.path.exists(frame["filepath"]) and frame["filepath"] != persistent_path:
            if not os.path.exists(persistent_path):
                shutil.copyfile(frame["filepath"], persistent_path)

        if os.path.exists(persistent_path):
            frame["filepath"] = persistent_path

        persistent_frames.append(frame)

    return persistent_frames
