from app.database import SessionLocal
from app.models import Video, TutorialStep
from app.services.step_frame_extractor import (
    extract_step_frames,
)


db = SessionLocal()

video = (
    db.query(Video)
    .filter(Video.id == 14)
    .first()
)

steps = (
    db.query(TutorialStep)
    .filter(
        TutorialStep.video_id == 14
    )
    .order_by(
        TutorialStep.step_number
    )
    .all()
)

step_data = [
    {
        "step": step.step_number,
        "start_time": step.start_time,
        "end_time": step.end_time,
    }
    for step in steps
]

print(
    "VIDEO:",
    video.filename,
)

print(
    "STEPS:",
    len(step_data),
)

for step in step_data:
    print(
        step["step"],
        step["start_time"],
        step["end_time"],
    )


frames = extract_step_frames(
    video_path=video.filepath,
    output_dir="frames/step_test",
    steps=step_data,
    padding_seconds=2.0,
    interval_seconds=1.0,
)

print(
    "FRAMES EXTRACTED:",
    len(frames),
)

for frame in frames:
    print(
        frame["step"],
        f"{frame['timestamp']:.2f}s",
        frame["filepath"],
    )


db.close()