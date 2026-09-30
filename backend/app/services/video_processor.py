import os
import math

import cv2

from ..config import VIDEO_ANALYSIS_MAX_FRAME_DIMENSION


class VideoDurationError(ValueError):
    """Video duration is missing, invalid, or exceeds the analysis limit."""


def validate_video_duration(duration, max_duration: float | None = None) -> float:
    try:
        normalized_duration = float(duration)
    except (TypeError, ValueError, OverflowError) as error:
        raise VideoDurationError(
            "Video duration could not be determined. Please upload a different video."
        ) from error

    if not math.isfinite(normalized_duration) or normalized_duration <= 0:
        raise VideoDurationError(
            "Video duration could not be determined. Please upload a different video."
        )

    if max_duration is not None and normalized_duration > max_duration:
        maximum_minutes = math.ceil(max_duration / 60)
        raise VideoDurationError(
            f"The current MVP supports videos up to {maximum_minutes} minutes."
        )

    return normalized_duration


def write_analysis_frame(frame, filepath: str) -> None:
    """Write a temporary analysis frame bounded by the configured dimensions."""
    height, width = frame.shape[:2]
    max_dimension = VIDEO_ANALYSIS_MAX_FRAME_DIMENSION
    largest_dimension = max(height, width)

    if largest_dimension <= max_dimension:
        cv2.imwrite(filepath, frame)
        return

    scale = max_dimension / largest_dimension
    resized = cv2.resize(
        frame,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    try:
        cv2.imwrite(filepath, resized)
    finally:
        del resized


def get_video_info(video_path: str):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        cap.release()
        raise VideoDurationError(
            "Video duration could not be determined. Please upload a different video."
        )

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if (
            not math.isfinite(fps)
            or fps <= 0
            or not math.isfinite(frame_count)
            or frame_count <= 0
        ):
            raise VideoDurationError(
                "Video duration could not be determined. Please upload a different video."
            )
        duration = validate_video_duration(frame_count / fps)
    finally:
        cap.release()

    return {
        "fps": fps,
        "frame_count": frame_count,
        "duration": duration,
    }


def extract_frames(
    video_path: str,
    output_dir: str,
    interval_seconds: float = 1.0,
    max_frames: int | None = None,
):
    os.makedirs(
        output_dir,
        exist_ok=True,
    )

    cap = cv2.VideoCapture(
        video_path
    )

    if not cap.isOpened():
        cap.release()
        raise ValueError(
            "Could not open video"
        )

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0:
            raise ValueError("Could not determine video FPS")

        duration = frame_count / fps if frame_count > 0 else 0
        interval_seconds = max(float(interval_seconds), 0.1)
        if max_frames is not None and max_frames > 0 and duration > 0:
            interval_seconds = max(interval_seconds, duration / max_frames)

        saved_frames = []
        timestamp = 0.0

        while timestamp < duration and (
            max_frames is None or len(saved_frames) < max_frames
        ):
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
            success, frame = cap.read()

            if not success:
                timestamp += interval_seconds
                continue

            actual_frame_index = cap.get(cv2.CAP_PROP_POS_FRAMES) - 1
            actual_timestamp = actual_frame_index / fps
            filepath = os.path.join(
                output_dir,
                f"frame_{actual_timestamp:.2f}.jpg",
            )
            write_analysis_frame(frame, filepath)
            saved_frames.append(
                {"filepath": filepath, "timestamp": actual_timestamp}
            )
            del frame
            timestamp += interval_seconds

        return saved_frames

    finally:
        cap.release()
