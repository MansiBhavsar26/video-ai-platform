import os

from app.services.code_frame_extractor import (
    extract_code_frames,
)


VIDEO_PATH = (
    r"uploads\5886b6f3ee97471bb64336917783c607.mp4"
)

OUTPUT_DIR = (
    r"frames\code_test"
)


frames = extract_code_frames(
    video_path=VIDEO_PATH,
    output_dir=OUTPUT_DIR,
    start_time=30.0,
    end_time=80.0,
    interval_seconds=2.0,
)


print(
    f"FRAMES EXTRACTED: {len(frames)}"
)

for frame in frames:
    print(
        f"{frame['timestamp']:.2f}s -> "
        f"{frame['filepath']}"
    )