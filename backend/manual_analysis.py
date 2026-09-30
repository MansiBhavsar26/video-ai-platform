from app.database import SessionLocal
from app.models import Video
from app.services.analyzer import analyze_video


def main():
    db = SessionLocal()

    try:
        video = db.query(Video).filter(
            Video.id == 1
        ).first()

        if not video:
            print("Video with ID 1 was not found.")
            return

        print("Starting video analysis...")
        print(f"Video: {video.filename}")
        print(f"Path: {video.filepath}")
        print(f"Duration: {video.duration:.2f} seconds")
        print(f"FPS: {video.fps:.2f}")

        result = analyze_video(
            video_path=video.filepath,
            video_id=video.id,
            db=db,
        )

        print()
        print("Analysis completed!")
        print(
            f"Frames processed: "
            f"{result['frames_processed']}"
        )
        print(
            f"Detections created: "
            f"{result['detections_created']}"
        )

    except Exception as e:
        db.rollback()
        print()
        print("Analysis failed:")
        print(e)

    finally:
        db.close()


if __name__ == "__main__":
    main()