import os

import cv2


def get_video_info(video_path: str):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        cap.release()
        raise ValueError(
            "Could not open video"
        )

    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps if fps > 0 else 0
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
            cv2.imwrite(filepath, frame)
            saved_frames.append(
                {"filepath": filepath, "timestamp": actual_timestamp}
            )
            del frame
            timestamp += interval_seconds

        return saved_frames

    finally:
        cap.release()
