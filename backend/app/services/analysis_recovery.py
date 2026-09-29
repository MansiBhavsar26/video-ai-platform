"""Retry local video analyses interrupted by a backend process restart."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..database import SessionLocal
from ..models import Video
from .analysis_job import run_analysis_job


logger = logging.getLogger(__name__)


def find_interrupted_analysis_video_ids() -> list[int]:
    """Find active local-media jobs; YouTube transcript jobs are separate."""
    db: Session = SessionLocal()
    try:
        videos = (
            db.query(Video)
            .filter(
                Video.status == "processing",
                Video.filepath.isnot(None),
                Video.source_type != "youtube",
            )
            .order_by(Video.id)
            .all()
        )
        return [video.id for video in videos]
    finally:
        db.close()


async def recover_interrupted_analyses() -> None:
    """Resume interrupted local analyses sequentially without delaying startup."""
    try:
        video_ids = await run_in_threadpool(find_interrupted_analysis_video_ids)
    except Exception:
        # Avoid logging database-driver exception text, which may contain a URL.
        logger.error("Unable to scan for interrupted video analyses at startup.")
        return

    if not video_ids:
        return

    logger.info("Retrying %d interrupted video analysis job(s).", len(video_ids))
    for video_id in video_ids:
        logger.info("Retrying interrupted analysis for video %s.", video_id)
        await run_in_threadpool(run_analysis_job, video_id)


def schedule_interrupted_analysis_recovery(app) -> asyncio.Task:
    """Start recovery in the current event loop and retain its task reference."""
    existing_task = getattr(app.state, "analysis_recovery_task", None)
    if existing_task is not None and not existing_task.done():
        return existing_task

    task = asyncio.create_task(recover_interrupted_analyses())
    app.state.analysis_recovery_task = task
    return task
