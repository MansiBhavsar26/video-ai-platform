from types import SimpleNamespace
from pathlib import Path
import wave

import numpy as np
import pytest

from app.services import transcription
from app.services.video_processor import VideoDurationError


class FakeModel:
    def __init__(self, chunk_segments=None):
        self.calls = []
        self.chunk_segments = chunk_segments or []

    def transcribe(self, path, **options):
        self.calls.append((path, options))
        segments = self.chunk_segments[len(self.calls) - 1] if self.chunk_segments else []
        return iter(segments), SimpleNamespace(language="en", language_probability=0.9)


def _run_with_mocked_chunks(monkeypatch, duration, model=None):
    model = model or FakeModel()
    ranges = []

    def write_chunk(path, output, start, end):
        ranges.append((start, end))
        with open(output, "wb") as audio_file:
            audio_file.write(b"mock")

    monkeypatch.setattr(transcription, "_write_audio_chunk", write_chunk)
    monkeypatch.setattr(transcription, "get_model", lambda: model)
    monkeypatch.setattr(transcription, "VIDEO_TRANSCRIPTION_CHUNK_SECONDS", 30)
    monkeypatch.setattr(transcription, "VIDEO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS", 2)
    result = transcription.transcribe_video(
        "mock-video.mp4",
        max_duration=1800,
        video_duration=duration,
    )
    return result, ranges, model


def test_30_minute_video_is_split_into_bounded_chunks(monkeypatch):
    _, ranges, model = _run_with_mocked_chunks(monkeypatch, 1800)

    assert len(ranges) > 1
    assert ranges[0] == (0, 30)
    assert ranges[-1][1] == 1800
    assert all(end - start <= 30 for start, end in ranges)
    assert all(path != "mock-video.mp4" for path, _ in model.calls)
    assert all(
        float(options["clip_timestamps"].split(",")[1]) <= 30
        for _, options in model.calls
    )


def test_10_minute_video_produces_multiple_chunks(monkeypatch):
    _, ranges, _ = _run_with_mocked_chunks(monkeypatch, 600)

    assert len(ranges) > 1
    assert ranges[0] == (0, 30)
    assert ranges[-1][1] == 600


def test_short_video_uses_one_chunk(monkeypatch):
    _, ranges, model = _run_with_mocked_chunks(monkeypatch, 12)

    assert ranges == [(0, 12)]
    assert len(model.calls) == 1


def test_chunk_timestamps_are_adjusted_to_absolute_video_time(monkeypatch):
    model = FakeModel(
        chunk_segments=[
            [SimpleNamespace(start=27, end=29, text="first")],
            [SimpleNamespace(start=2, end=4, text="second")],
        ]
    )
    result, ranges, _ = _run_with_mocked_chunks(monkeypatch, 45, model)

    assert ranges[:2] == [(0, 30), (28, 45)]
    assert result["segments"] == [
        {"start_time": 27.0, "end_time": 29.0, "text": "first"},
        {"start_time": 30.0, "end_time": 32.0, "text": "second"},
    ]


def test_obvious_identical_overlap_segment_is_removed(monkeypatch):
    model = FakeModel(
        chunk_segments=[
            [SimpleNamespace(start=27, end=29, text="Save the file.")],
            [SimpleNamespace(start=0.2, end=1.8, text="Save the file.")],
        ]
    )
    result, _, _ = _run_with_mocked_chunks(monkeypatch, 45, model)

    assert len(result["segments"]) == 1


def test_legitimate_repeated_phrase_outside_overlap_is_preserved(monkeypatch):
    first = {"start_time": 1.0, "end_time": 2.0, "text": "Repeat this"}
    second = {"start_time": 10.0, "end_time": 11.0, "text": "Repeat this"}

    assert not transcription._is_duplicate_overlap(second, [first], overlap=2)


def test_whisper_model_is_loaded_once_for_the_full_chunk_job(monkeypatch):
    model = FakeModel()
    load_calls = []
    monkeypatch.setattr(transcription, "_write_audio_chunk", lambda *args: open(args[1], "wb").close())
    monkeypatch.setattr(transcription, "get_model", lambda: load_calls.append(True) or model)

    transcription.transcribe_video("video.mp4", 1800, video_duration=80)

    assert len(load_calls) == 1
    assert len(model.calls) > 1
    assert all(options["beam_size"] == 1 for _, options in model.calls)
    assert all(options["vad_filter"] is False for _, options in model.calls)


def test_temporary_chunks_are_deleted_after_success(monkeypatch):
    paths = []
    model = FakeModel()

    def write_chunk(path, output, start, end):
        paths.append(output)
        with open(output, "wb") as audio_file:
            audio_file.write(b"mock")

    monkeypatch.setattr(transcription, "_write_audio_chunk", write_chunk)
    monkeypatch.setattr(transcription, "get_model", lambda: model)
    transcription.transcribe_video("video.mp4", 1800, video_duration=40)

    assert paths
    assert all(not Path(path).exists() for path in paths)


def test_temporary_chunk_and_model_are_released_after_failure(monkeypatch):
    path = {}
    model = FakeModel()

    def write_chunk(video, output, start, end):
        path["value"] = output
        with open(output, "wb") as audio_file:
            audio_file.write(b"mock")

    monkeypatch.setattr(transcription, "_write_audio_chunk", write_chunk)
    monkeypatch.setattr(transcription, "get_model", lambda: model)
    monkeypatch.setattr(transcription, "release_model", lambda: path.setdefault("released", True))
    monkeypatch.setattr(
        model,
        "transcribe",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("mock failure")),
    )

    with pytest.raises(RuntimeError, match="mock failure"):
        transcription.transcribe_video("video.mp4", 1800, video_duration=20)

    assert path["released"]
    assert not Path(path["value"]).exists()


@pytest.mark.parametrize("duration", [0, None, float("nan"), float("inf"), "bad"])
def test_invalid_source_duration_is_rejected_before_model_load(monkeypatch, duration):
    monkeypatch.setattr(
        transcription,
        "get_model",
        lambda: pytest.fail("invalid duration reached Whisper"),
    )

    with pytest.raises((ValueError, VideoDurationError)):
        transcription.transcribe_video("video.mp4", 1800, video_duration=duration)


def test_source_duration_above_maximum_is_rejected_before_model_load(monkeypatch):
    monkeypatch.setattr(
        transcription,
        "get_model",
        lambda: pytest.fail("over-limit duration reached Whisper"),
    )

    with pytest.raises(VideoDurationError):
        transcription.transcribe_video("video.mp4", 1800, video_duration=1801)


def test_pyav_chunk_extraction_writes_only_requested_audio_interval(tmp_path):
    source = tmp_path / "source.wav"
    chunk = tmp_path / "chunk.wav"
    sample_rate = transcription.SAMPLE_RATE
    samples = np.zeros(sample_rate * 8, dtype=np.int16)
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())

    transcription._write_audio_chunk(str(source), str(chunk), 2, 5)

    with wave.open(str(chunk), "rb") as audio:
        assert audio.getframerate() == sample_rate
        assert audio.getnframes() == 3 * sample_rate
