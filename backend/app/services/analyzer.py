import logging
import os
from collections import Counter

from ..config import ENABLE_OBJECT_DETECTION, FRAMES_DIR
from .smart_sampling import smart_sample_video
from .detector import detect_objects, release_model as release_detector_model
from .ocr import extract_text
from .ocr_cleaner import clean_ocr_text
from .vision import generate_video_description
from .timeline import build_timeline, detect_scene_changes
from .developer_action_pipeline import build_developer_action_timeline
from .evidence_fusion import fuse_evidence
from .evidence_storage import save_video_evidence
from .evidence_classifier import (
    classify_evidence,
    get_evidence_confidence,
)
from ..models import Detection
from .analysis_diagnostics import analysis_stage


OCR_FALLBACK_FRAME_INTERVAL = 3
OCR_SCREEN_LABELS = {"tv", "laptop", "cell phone"}
logger = logging.getLogger(__name__)


def _extract_ocr_text_safely(frame_path: str, video_id: int | None = None) -> str:
    try:
        return extract_text(frame_path, video_id=video_id)
    except Exception as error:
        logger.warning(
            "[analysis] video=%s stage=ocr failed error_type=%s; continuing without OCR.",
            video_id if video_id is not None else "unknown",
            type(error).__name__,
        )
        return ""


def _should_run_ocr(frame_index: int, detections: list[dict]) -> bool:
    """OCR likely screen frames plus a periodic fallback when YOLO misses them."""
    if frame_index % OCR_FALLBACK_FRAME_INTERVAL == 0:
        return True
    return any(
        str(detection.get("label", "")).lower() in OCR_SCREEN_LABELS
        for detection in detections
    )


def analyze_video(
    video_path: str,
    video_id: int,
    db,
    video_duration: float,
    transcript_segments: list[dict] | None = None,
    frames_root: str | None = None,
):

    if transcript_segments is None:
        transcript_segments = []

    output_dir = os.path.join(
        frames_root or FRAMES_DIR,
        str(video_id),
    )

    with analysis_stage(video_id, "frame_extraction") as metrics:
        frames = smart_sample_video(
            video_path=video_path,
            output_dir=output_dir,
        )
        metrics["frames"] = len(frames)

    detection_count = 0

    ocr_results = []
    ocr_frame_selection = []
    object_counts = Counter()
    detection_stats = {}
    visual_events = []

    # --------------------------------------------------
    # Detect objects in each selected frame
    # --------------------------------------------------

    if ENABLE_OBJECT_DETECTION:
        with analysis_stage(video_id, "detection") as metrics:
            try:
                for frame_index, frame in enumerate(frames):
                    detections = detect_objects(frame["filepath"])
                    ocr_frame_selection.append(_should_run_ocr(frame_index, detections))
                    for detection in detections:
                        timestamp = frame["timestamp"]
                        label = detection["label"]
                        confidence = float(detection["confidence"])
                        stats = detection_stats.get(label)
                        if stats is None:
                            stats = {
                                "appearances": 0,
                                "first_seen": timestamp,
                                "last_seen": timestamp,
                                "confidence_total": 0.0,
                            }
                            detection_stats[label] = stats
                        stats["appearances"] += 1
                        stats["last_seen"] = timestamp
                        stats["confidence_total"] += confidence
                        object_counts[label] += 1
                        visual_events.append((timestamp, label))
                        db.add(
                            Detection(
                                video_id=video_id,
                                timestamp=timestamp,
                                label=label,
                                confidence=confidence,
                                x1=detection["x1"],
                                y1=detection["y1"],
                                x2=detection["x2"],
                                y2=detection["y2"],
                            )
                        )
                        detection_count += 1

                    del detections
            finally:
                release_detector_model()
            db.flush()
            metrics["frames"] = len(frames)
            metrics["detections"] = detection_count
    else:
        logger.info("[analysis] video=%s object_detection disabled", video_id)
        with analysis_stage(video_id, "detection") as metrics:
            ocr_frame_selection = [
                frame_index % OCR_FALLBACK_FRAME_INTERVAL == 0
                for frame_index in range(len(frames))
            ]
            metrics["frames"] = 0
            metrics["detections"] = 0

    # --------------------------------------------------
    # OCR selected frames after releasing the detector model
    # --------------------------------------------------

    with analysis_stage(video_id, "ocr") as metrics:
        for frame_index, frame in enumerate(frames):
            if not ocr_frame_selection[frame_index]:
                continue

            raw_text = _extract_ocr_text_safely(frame["filepath"], video_id)
            text = clean_ocr_text(raw_text)
            if text:
                evidence_type = classify_evidence(text)
                ocr_results.append(
                    {
                        "timestamp": frame["timestamp"],
                        "text": text,
                        "evidence_type": evidence_type,
                        "source": "video_frame",
                        "confidence": get_evidence_confidence(evidence_type),
                    }
                )
            del raw_text, text

        metrics["frames_selected"] = sum(ocr_frame_selection)
        metrics["evidence_records"] = len(ocr_results)

    with analysis_stage(video_id, "evidence") as metrics:
        object_summary = [
            {
                "label": label,
                "appearances": stats["appearances"],
                "first_seen": stats["first_seen"],
                "last_seen": stats["last_seen"],
                "average_confidence": round(
                    stats["confidence_total"] / stats["appearances"],
                    3,
                ),
            }
            for label, stats in detection_stats.items()
        ]
        object_summary.sort(
            key=lambda item: (-item["appearances"], item["label"])
        )
        scene_changes = detect_scene_changes(frames)
        timeline = build_timeline(object_summary, ocr_results, scene_changes)

        developer_actions = build_developer_action_timeline(
            segments=transcript_segments,
        )
        if developer_actions is None:
            developer_actions = []

        fused_evidence = fuse_evidence(
            transcript_segments=transcript_segments,
            ocr_results=ocr_results,
            developer_actions=developer_actions,
            visual_events=visual_events,
            time_window_seconds=3.0,
        )

        db.commit()

        save_video_evidence(
            db=db,
            video_id=video_id,
            evidence=ocr_results,
        )
        metrics["evidence_records"] = len(ocr_results)
        metrics["fused_evidence_records"] = len(fused_evidence)
        metrics["developer_actions"] = len(developer_actions)

    # --------------------------------------------------
    # Generate local video description
    # --------------------------------------------------

    with analysis_stage(video_id, "video_description"):
        description = generate_video_description(
            frames=frames,
            detections=object_counts,
            video_duration=video_duration,
            ocr_results=ocr_results,
        )

    return {
        "frames_processed": len(frames),
        "detections_created": detection_count,
        "description": description,
        "ocr_results": ocr_results,
        "object_summary": object_summary,
        "scene_changes": scene_changes,
        "timeline": timeline,
        "developer_actions": developer_actions,
        "fused_evidence": fused_evidence,
    }
