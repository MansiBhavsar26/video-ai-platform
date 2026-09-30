import os

from ..config import FRAMES_DIR
from .smart_sampling import smart_sample_video
from .detector import detect_objects, release_model as release_detector_model
from .ocr import extract_text
from .ocr_cleaner import clean_ocr_text
from .vision import generate_video_description
from .timeline import aggregate_detections, build_timeline, detect_scene_changes
from .developer_action_pipeline import build_developer_action_timeline
from .evidence_fusion import fuse_evidence
from .evidence_storage import save_video_evidence
from .evidence_classifier import (
    classify_evidence,
    get_evidence_confidence,
)
from ..models import Detection


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

    frames = smart_sample_video(
        video_path=video_path,
        output_dir=output_dir,
    )

    detection_count = 0

    all_detections = []

    ocr_results = []

    # --------------------------------------------------
    # Analyze every frame
    # --------------------------------------------------

    try:
        for frame in frames:
            detections = detect_objects(frame["filepath"])
            for detection in detections:
                timestamp = frame["timestamp"]
                all_detections.append({**detection, "timestamp": timestamp})
                db.add(
                    Detection(
                        video_id=video_id,
                        timestamp=timestamp,
                        label=detection["label"],
                        confidence=detection["confidence"],
                        x1=detection["x1"],
                        y1=detection["y1"],
                        x2=detection["x2"],
                        y2=detection["y2"],
                    )
                )
                detection_count += 1

            raw_text = extract_text(frame["filepath"])
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

            del detections, raw_text, text
    finally:
        release_detector_model()

    object_summary = aggregate_detections(all_detections)
    scene_changes = detect_scene_changes(frames)
    timeline = build_timeline(object_summary, ocr_results, scene_changes)

    visual_events = []
    if all_detections:
        visual_events = [
            {
                "timestamp": detection["timestamp"],
                "label": detection["label"],
            }
            for detection in all_detections
            if isinstance(detection, dict)
            and "timestamp" in detection
            and "label" in detection
        ]

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

    # --------------------------------------------------
    # Generate local video description
    # --------------------------------------------------

    description = generate_video_description(
        frames=frames,
        detections=all_detections,
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
