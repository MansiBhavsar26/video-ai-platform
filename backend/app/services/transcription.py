from faster_whisper import WhisperModel
import gc


MODEL_SIZE = "tiny"


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


def transcribe_video(
    video_path: str,
    max_duration: float | None = None,
):
    model = get_model()

    transcribe_options = {
        "beam_size": 1,
        "vad_filter": True,
    }

    if max_duration is not None:
        transcribe_options[
            "clip_timestamps"
        ] = f"0,{max_duration}"

    segments, info = model.transcribe(
        video_path,
        **transcribe_options,
    )

    results = []

    for segment in segments:
        text = segment.text.strip()

        if not text:
            continue

        results.append(
            {
                "start_time": float(
                    segment.start
                ),
                "end_time": float(
                    segment.end
                ),
                "text": text,
            }
        )

    return {
        "language": info.language,
        "language_probability": float(
            info.language_probability
        ),
        "segments": results,
    }
