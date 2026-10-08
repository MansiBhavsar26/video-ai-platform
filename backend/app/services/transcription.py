import gc
import logging
import math
import tempfile
import wave
from pathlib import Path

import av
import numpy as np
from faster_whisper import WhisperModel

from ..config import (
    VIDEO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS,
    VIDEO_TRANSCRIPTION_CHUNK_SECONDS,
)
from .video_processor import get_video_info, validate_video_duration


MODEL_SIZE = "tiny"
SAMPLE_RATE = 16_000

logger = logging.getLogger(__name__)

_model = None


def get_model():
    global _model

    if _model is None:
        _model = WhisperModel(
            MODEL_SIZE,
            device="cpu",
            compute_type="int8",
        )

    return _model


def release_model():
    """Release the cached Whisper model before loading the vision model."""
    global _model

    model = _model
    _model = None
    was_loaded = model is not None
    del model
    if was_loaded:
        gc.collect()


def _chunk_ranges(
    duration: float,
    chunk_seconds: float,
    overlap_seconds: float,
):
    if not math.isfinite(chunk_seconds) or chunk_seconds <= 0:
        raise ValueError("Transcription chunk size must be a positive finite value.")
    if (
        not math.isfinite(overlap_seconds)
        or overlap_seconds < 0
        or overlap_seconds >= chunk_seconds
    ):
        raise ValueError("Transcription chunk overlap must be less than chunk size.")

    step = chunk_seconds - overlap_seconds
    start = 0.0
    while start < duration:
        end = min(start + chunk_seconds, duration)
        yield start, end
        if end >= duration:
            break
        start += step


def _write_audio_chunk(
    video_path: str,
    output_path: str,
    start_seconds: float,
    end_seconds: float,
) -> None:
    """Decode only the requested interval and write mono 16 kHz PCM to disk."""
    with av.open(video_path, mode="r") as container:
        audio_stream = next(
            (stream for stream in container.streams if stream.type == "audio"),
            None,
        )
        if audio_stream is None:
            raise ValueError("The video does not contain an audio track.")

        stream_time_base = float(audio_stream.time_base)
        stream_origin = (
            float(audio_stream.start_time * audio_stream.time_base)
            if audio_stream.start_time is not None
            else 0.0
        )
        seek_timestamp = int((stream_origin + start_seconds) / stream_time_base)
        container.seek(
            seek_timestamp,
            stream=audio_stream,
            backward=True,
            any_frame=False,
        )

        resampler = av.audio.resampler.AudioResampler(
            format="s16",
            layout="mono",
            rate=SAMPLE_RATE,
        )
        cursor_seconds = None
        samples_written = 0
        target_samples = max(
            0,
            int(round((end_seconds - start_seconds) * SAMPLE_RATE)),
        )

        with wave.open(output_path, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)

            for decoded_frame in container.decode(audio_stream):
                resampled_frames = resampler.resample(decoded_frame)
                for frame in resampled_frames:
                    if frame.pts is not None and frame.time_base is not None:
                        frame_start = float(frame.pts * frame.time_base) - stream_origin
                    elif cursor_seconds is not None:
                        frame_start = cursor_seconds
                    else:
                        frame_start = max(start_seconds, 0.0)

                    samples = frame.to_ndarray().reshape(-1)
                    frame_end = frame_start + len(samples) / SAMPLE_RATE
                    cursor_seconds = frame_end

                    if frame_end <= start_seconds:
                        del samples, frame, resampled_frames
                        continue
                    if frame_start >= end_seconds:
                        del samples
                        break

                    first_sample = max(
                        0,
                        int(math.ceil((start_seconds - frame_start) * SAMPLE_RATE)),
                    )
                    last_sample = min(
                        len(samples),
                        int(math.ceil((end_seconds - frame_start) * SAMPLE_RATE)),
                        first_sample + target_samples - samples_written,
                    )
                    if last_sample > first_sample:
                        selected = samples[first_sample:last_sample]
                        output.writeframesraw(selected.tobytes())
                        samples_written += len(selected)
                        del selected

                    del samples
                    if frame_end >= end_seconds:
                        break

                if cursor_seconds is not None and cursor_seconds >= end_seconds:
                    break

            # Flush delayed resampler samples that still belong to this interval.
            for frame in resampler.resample(None):
                frame_start = (
                    float(frame.pts * frame.time_base) - stream_origin
                    if frame.pts is not None and frame.time_base is not None
                    else cursor_seconds
                )
                if frame_start is None or frame_start >= end_seconds:
                    continue
                samples = frame.to_ndarray().reshape(-1)
                first_sample = max(
                    0,
                    int(math.ceil((start_seconds - frame_start) * SAMPLE_RATE)),
                )
                last_sample = min(
                    len(samples),
                    int(math.ceil((end_seconds - frame_start) * SAMPLE_RATE)),
                    first_sample + target_samples - samples_written,
                )
                if last_sample > first_sample:
                    selected = samples[first_sample:last_sample]
                    output.writeframesraw(selected.tobytes())
                    samples_written += len(selected)
                    del selected
                cursor_seconds = frame_start + len(samples) / SAMPLE_RATE
                del samples

        del resampler

    if samples_written == 0:
        raise ValueError("No audio samples were found in the requested chunk.")


def _normalized_text(text: str) -> str:
    return " ".join("".join(char.lower() for char in text if char.isalnum()).split())


def _is_duplicate_overlap(candidate: dict, previous_segments: list[dict], overlap: float) -> bool:
    """Drop only text-identical segments substantially repeated in the overlap."""
    if overlap <= 0:
        return False

    candidate_text = _normalized_text(candidate["text"])
    if not candidate_text:
        return False

    candidate_duration = max(0.0, candidate["end_time"] - candidate["start_time"])
    for previous in reversed(previous_segments):
        if candidate["start_time"] - previous["end_time"] > overlap + 1.0:
            break
        if _normalized_text(previous["text"]) != candidate_text:
            continue

        intersection = max(
            0.0,
            min(candidate["end_time"], previous["end_time"])
            - max(candidate["start_time"], previous["start_time"]),
        )
        shorter_duration = min(
            candidate_duration,
            max(0.0, previous["end_time"] - previous["start_time"]),
        )
        if shorter_duration == 0 or intersection / shorter_duration >= 0.5:
            return True

    return False


def transcribe_video(
    video_path: str,
    max_duration: float | None = None,
    video_duration: float | None = None,
):
    if max_duration is not None:
        try:
            max_duration = float(max_duration)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(
                "A valid maximum transcription duration is required."
            ) from error
        if not math.isfinite(max_duration) or max_duration <= 0:
            raise ValueError("A valid maximum transcription duration is required.")

    if video_duration is None:
        video_duration = get_video_info(video_path)["duration"]
    duration = validate_video_duration(video_duration)
    if max_duration is not None:
        duration = min(duration, max_duration)

    chunk_seconds = float(VIDEO_TRANSCRIPTION_CHUNK_SECONDS)
    overlap_seconds = float(VIDEO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS)
    ranges = list(_chunk_ranges(duration, chunk_seconds, overlap_seconds))
    logger.info(
        "Starting transcription for %s: duration=%.2fs chunks=%s chunk_seconds=%.2f",
        video_path,
        duration,
        len(ranges),
        chunk_seconds,
    )
    model = get_model()
    results = []
    language = None
    language_probability = 0.0

    try:
        for chunk_number, (chunk_start, chunk_end) in enumerate(ranges, start=1):
            temporary_path = None
            segments = None
            info = None
            segment = None
            try:
                logger.info(
                    "Transcription chunk %s/%s: extracting audio %.2fs-%.2fs",
                    chunk_number,
                    len(ranges),
                    chunk_start,
                    chunk_end,
                )
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as file:
                    temporary_path = file.name

                _write_audio_chunk(
                    video_path,
                    temporary_path,
                    chunk_start,
                    chunk_end,
                )

                logger.info(
                    "Transcription chunk %s/%s: transcribing %.2fs-%.2fs",
                    chunk_number,
                    len(ranges),
                    chunk_start,
                    chunk_end,
                )
                segments, info = model.transcribe(
                    temporary_path,
                    beam_size=1,
                    vad_filter=True,
                    language=language,
                )
                if language is None:
                    language = info.language
                    language_probability = float(info.language_probability)

                for segment in segments:
                    text = segment.text.strip()
                    if not text:
                        continue

                    candidate = {
                        "start_time": max(
                            0.0,
                            chunk_start + float(segment.start),
                        ),
                        "end_time": min(
                            duration,
                            chunk_start + float(segment.end),
                        ),
                        "text": text,
                    }
                    if not _is_duplicate_overlap(
                        candidate,
                        results,
                        overlap_seconds,
                    ):
                        results.append(candidate)
                logger.info(
                    "Completed transcription chunk %s/%s: %.2fs-%.2fs",
                    chunk_number,
                    len(ranges),
                    chunk_start,
                    chunk_end,
                )
            except Exception as error:
                logger.exception(
                    "Transcription chunk %s/%s failed: %.2fs-%.2fs",
                    chunk_number,
                    len(ranges),
                    chunk_start,
                    chunk_end,
                )
                raise RuntimeError(
                    f"Transcription chunk {chunk_number}/{len(ranges)} "
                    f"failed ({chunk_start:.2f}s-{chunk_end:.2f}s)."
                ) from error
            finally:
                del segment, segments, info
                if temporary_path is not None:
                    Path(temporary_path).unlink(missing_ok=True)
                gc.collect()

    except Exception:
        release_model()
        raise

    results.sort(key=lambda item: item["start_time"])
    logger.info("Transcription completed. Segments: %s", len(results))

    return {
        "language": language or "und",
        "language_probability": language_probability,
        "segments": results,
    }
