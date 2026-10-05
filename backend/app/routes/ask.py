from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Video
from ..services.video_qa import (
    NO_ANSWER,
    QuestionAnsweringUnavailable,
    answer_video_question,
)


router = APIRouter(
    prefix="/videos",
    tags=["ask"],
)


class AskRequest(BaseModel):
    question: str = Field(max_length=1000)


@router.post("/{video_id}/ask")
def ask_video(
    video_id: int,
    payload: AskRequest,
    db: Session = Depends(get_db),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        result = answer_video_question(
            db=db,
            video_id=video_id,
            question=question,
        )
    except QuestionAnsweringUnavailable as error:
        raise HTTPException(
            status_code=503,
            detail="Video Q&A is temporarily unavailable.",
        ) from error

    return {
        "video_id": video_id,
        "question": question,
        "answerable": result["answerable"],
        "answer": result["answer"] if result["answerable"] else NO_ANSWER,
        "evidence": result["evidence"],
    }
