from app.services.code_frame_extractor import (
    extract_code_frames,
)

from app.services.code_frame_selector import (
    select_chronological_frames,
)


VIDEO_PATH = (
    r"uploads\youtube\S66rHpyU-Eg.mp4"
)

OUTPUT_DIR = (
    "test_youtube_app_frames"
)


frames = extract_code_frames(
    video_path=VIDEO_PATH,
    output_dir=OUTPUT_DIR,
    start_time=1888.88,
    end_time=1913.07,
    interval_seconds=2.0,
)


print(
    "TOTAL FRAMES:",
    len(frames),
)


selected = select_chronological_frames(
    frames,
    max_frames=6,
)


print()
print("=" * 70)
print("SELECTED CODE FRAMES")
print("=" * 70)


for index, frame in enumerate(
    selected,
    start=1,
):

    print()
    print(
        f"{index}. "
        f"{frame['timestamp']:.2f}s"
    )

    print(
        f"   SIZE: "
        f"{frame['width']}x"
        f"{frame['height']}"
    )

    print(
        f"   SHARPNESS: "
        f"{frame['sharpness']}"
    )

    print(
        f"   FILE: "
        f"{frame['filepath']}"
    )