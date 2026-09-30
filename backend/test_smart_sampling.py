import os
from pathlib import Path

import cv2
import numpy as np

from app.services.smart_sampling import smart_sample_frames, smart_sample_video


def _make_frame(path, base_color=(0, 0, 0), stripe=False):
    image = np.full((64, 64, 3), base_color, dtype=np.uint8)

    if stripe:
        image[:, 32:, :] = (255, 255, 255)

    cv2.imwrite(path, image)

    return path


def test_smart_sampling_no_frames_returns_empty():
    assert smart_sample_frames([]) == []


def test_smart_sampling_single_frame_returns_that_frame(tmp_path):
    frame_path = tmp_path / "single.jpg"
    _make_frame(str(frame_path), base_color=(10, 20, 30))

    result = smart_sample_frames([
        {"filepath": str(frame_path), "timestamp": 0.0},
    ])

    assert result == [
        {"filepath": str(frame_path), "timestamp": 0.0},
    ]


def test_smart_sampling_similar_frames_are_not_all_marked_as_changes(tmp_path):
    image_dir = tmp_path / "similar"
    image_dir.mkdir()

    frame_paths = []
    for index in range(5):
        frame_path = image_dir / f"frame_{index}.jpg"
        _make_frame(
            str(frame_path),
            base_color=(20 + index, 30 + index, 40 + index),
            stripe=False,
        )
        frame_paths.append(frame_path)

    frames = [
        {"filepath": str(path), "timestamp": float(index * 5.0)}
        for index, path in enumerate(frame_paths)
    ]

    result = smart_sample_frames(
        frames,
        coarse_interval_seconds=5.0,
        visual_change_threshold=12.0,
        refinement_window_seconds=2.0,
        refinement_interval_seconds=1.0,
        min_frame_gap_seconds=8.0,
    )

    assert len(result) < len(frames)
    assert len(result) <= 3


def test_smart_sampling_detects_meaningful_visual_change(tmp_path):
    image_dir = tmp_path / "change"
    image_dir.mkdir()

    first = _make_frame(str(image_dir / "frame_0.jpg"), base_color=(0, 0, 0))
    second = _make_frame(str(image_dir / "frame_1.jpg"), base_color=(255, 255, 255))
    third = _make_frame(str(image_dir / "frame_2.jpg"), base_color=(255, 255, 255))

    frames = [
        {"filepath": first, "timestamp": 0.0},
        {"filepath": second, "timestamp": 10.0},
        {"filepath": third, "timestamp": 20.0},
    ]

    result = smart_sample_frames(
        frames,
        coarse_interval_seconds=10.0,
        visual_change_threshold=5.0,
        refinement_window_seconds=2.0,
        refinement_interval_seconds=1.0,
        min_frame_gap_seconds=1.0,
    )

    assert any(frame["timestamp"] == 10.0 for frame in result)
    assert len(result) >= 2


def test_smart_sampling_video_returns_persistent_frames_under_output_dir(tmp_path):
    video_path = tmp_path / "synthetic.mp4"
    output_dir = tmp_path / "output"

    width, height = 128, 72
    fps = 10
    duration = 12
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))

    try:
        for second in range(duration):
            for _ in range(fps):
                image = np.full((height, width, 3), 20, dtype=np.uint8)
                if second >= 6:
                    image[:, :, 0] = 220
                    image[:, :, 1] = 220
                    image[:, :, 2] = 220
                writer.write(image)
    finally:
        writer.release()

    result = smart_sample_video(
        video_path=str(video_path),
        output_dir=str(output_dir),
        coarse_interval_seconds=5.0,
        visual_change_threshold=18.0,
        refinement_window_seconds=3.0,
        refinement_interval_seconds=1.0,
        min_frame_gap_seconds=1.0,
    )

    assert result
    assert len(result) >= 2

    for frame in result:
        frame_path = Path(frame["filepath"])
        assert frame_path.exists()
        assert os.path.commonpath(
            [str(frame_path.resolve()), str(output_dir.resolve())]
        ) == str(output_dir.resolve())

    timestamps = [frame["timestamp"] for frame in result]
    assert timestamps == sorted(timestamps)


def test_smart_sampling_respects_frame_memory_limit(tmp_path):
    video_path = tmp_path / "bounded.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 10, (64, 48))
    try:
        for index in range(300):
            writer.write(np.full((48, 64, 3), index % 255, dtype=np.uint8))
    finally:
        writer.release()

    frames = smart_sample_video(
        str(video_path),
        str(tmp_path / "bounded-frames"),
        coarse_interval_seconds=1,
        max_frames=4,
    )

    assert 0 < len(frames) <= 4


def test_smart_sampling_removes_duplicate_timestamps_and_sorts_them():
    frames = [
        {"filepath": "b.jpg", "timestamp": 10.0},
        {"filepath": "a.jpg", "timestamp": 0.0},
        {"filepath": "c.jpg", "timestamp": 10.0},
        {"filepath": "d.jpg", "timestamp": 5.0},
    ]

    result = smart_sample_frames(frames)

    assert [frame["timestamp"] for frame in result] == [0.0, 5.0, 10.0]


def test_smart_sampling_does_not_keep_large_in_memory_frame_arrays():
    frames = [
        {"filepath": "frame_0.jpg", "timestamp": 0.0},
        {"filepath": "frame_10.jpg", "timestamp": 10.0},
        {"filepath": "frame_20.jpg", "timestamp": 20.0},
    ]

    result = smart_sample_frames(frames, visual_change_threshold=0.1)

    assert all("frame" not in frame for frame in result)
    assert all("filepath" in frame and "timestamp" in frame for frame in result)
