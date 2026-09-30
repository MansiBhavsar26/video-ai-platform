from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Video
from app.routes.videos import _claim_analysis


def test_atomic_analysis_claim_prevents_duplicate_processing():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    try:
        with sessions() as setup:
            video = Video(
                filename="sample.mp4",
                duration=10,
                fps=30,
                status="uploaded",
                source_type="upload",
            )
            setup.add(video)
            setup.commit()
            video_id = video.id

        with sessions() as first_request, sessions() as second_request:
            assert _claim_analysis(first_request, video_id)
            first_request.commit()

            assert not _claim_analysis(second_request, video_id)
            second_request.rollback()

        with sessions() as retry_request:
            retry_request.query(Video).filter(Video.id == video_id).update(
                {Video.status: "completed"}
            )
            retry_request.commit()

        with sessions() as completed_retry:
            assert _claim_analysis(completed_retry, video_id)
            completed_retry.rollback()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
