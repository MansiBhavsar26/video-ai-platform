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


def _run_with_mocked_chunks(monkeypatch, duration, model=None, max_duration=1800):
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
        max_duration=max_duration,
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
    assert all(options["beam_size"] == 1 for _, options in model.calls)
    assert all(options["vad_filter"] is True for _, options in model.calls)
    assert all("clip_timestamps" not in options for _, options in model.calls)


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
            [SimpleNamespace(start=2, end=5, text="first")],
            [SimpleNamespace(start=3, end=6, text="second")],
        ]
    )
    result, ranges, _ = _run_with_mocked_chunks(monkeypatch, 45, model)

    assert ranges[:2] == [(0, 30), (28, 45)]
    assert result["segments"] == [
        {"start_time": 2.0, "end_time": 5.0, "text": "first"},
        {"start_time": 31.0, "end_time": 34.0, "text": "second"},
    ]


def test_segments_are_sorted_and_output_contract_is_preserved(monkeypatch):
    model = FakeModel(
        chunk_segments=[
            [
                SimpleNamespace(start=12, end=14, text="later"),
                SimpleNamespace(start=2, end=5, text="earlier"),
            ],
            [SimpleNamespace(start=3, end=6, text="next chunk")],
        ]
    )

    result, _, _ = _run_with_mocked_chunks(monkeypatch, 45, model)

    assert set(result) == {"language", "language_probability", "segments"}
    assert result["language"] == "en"
    assert result["language_probability"] == 0.9
    assert result["segments"] == [
        {"start_time": 2.0, "end_time": 5.0, "text": "earlier"},
        {"start_time": 12.0, "end_time": 14.0, "text": "later"},
        {"start_time": 31.0, "end_time": 34.0, "text": "next chunk"},
    ]


def test_max_duration_limits_processing_without_rejecting_long_source(monkeypatch):
    _, ranges, _ = _run_with_mocked_chunks(
        monkeypatch,
        duration=100,
        max_duration=45,
    )

    assert ranges == [(0, 30), (28, 45)]


def test_none_max_duration_uses_actual_video_duration(monkeypatch):
    model = FakeModel()
    ranges = []

    def write_chunk(path, output, start, end):
        ranges.append((start, end))
        Path(output).write_bytes(b"mock")

    monkeypatch.setattr(transcription, "_write_audio_chunk", write_chunk)
    monkeypatch.setattr(transcription, "get_model", lambda: model)
    monkeypatch.setattr(
        transcription,
        "get_video_info",
        lambda path: {"duration": 65},
    )
    monkeypatch.setattr(transcription, "VIDEO_TRANSCRIPTION_CHUNK_SECONDS", 30)
    monkeypatch.setattr(transcription, "VIDEO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS", 0)

    transcription.transcribe_video("mock-video.mp4")

    assert ranges == [(0, 30), (30, 60), (60, 65)]


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
    assert all(options["vad_filter"] is True for _, options in model.calls)
    assert model.calls[0][1]["language"] is None
    assert all(options["language"] == "en" for _, options in model.calls[1:])


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

    with pytest.raises(
        RuntimeError,
        match="Transcription chunk 1/1 failed",
    ) as error:
        transcription.transcribe_video("video.mp4", 1800, video_duration=20)

    assert str(error.value.__cause__) == "mock failure"
    assert path["released"]
    assert not Path(path["value"]).exists()


def test_invalid_audio_chunk_fails_clearly_and_cleans_temporary_file(monkeypatch):
    paths = []

    def reject_audio(video, output, start, end):
        paths.append(output)
        raise ValueError("The video does not contain an audio track.")

    monkeypatch.setattr(transcription, "_write_audio_chunk", reject_audio)
    monkeypatch.setattr(transcription, "get_model", lambda: FakeModel())

    with pytest.raises(RuntimeError, match="Transcription chunk 1/1 failed"):
        transcription.transcribe_video("invalid-video.mp4", video_duration=20)

    assert paths
    assert all(not Path(path).exists() for path in paths)


@pytest.mark.parametrize("duration", [0, None, float("nan"), float("inf"), "bad"])
def test_invalid_source_duration_is_rejected_before_model_load(monkeypatch, duration):
    monkeypatch.setattr(
        transcription,
        "get_model",
        lambda: pytest.fail("invalid duration reached Whisper"),
    )

    with pytest.raises((ValueError, VideoDurationError)):
        transcription.transcribe_video("video.mp4", 1800, video_duration=duration)


def test_source_duration_above_maximum_is_capped_before_transcription(monkeypatch):
    ranges = []

    def write_chunk(path, output, start, end):
        ranges.append((start, end))

    class EmptyModel:
        def transcribe(self, path, **options):
            return iter(()), SimpleNamespace(language="en", language_probability=0.9)

    monkeypatch.setattr(transcription, "_write_audio_chunk", write_chunk)
    monkeypatch.setattr(
        transcription,
        "get_model",
        lambda: EmptyModel(),
    )
    monkeypatch.setattr(transcription, "VIDEO_TRANSCRIPTION_CHUNK_SECONDS", 30)
    monkeypatch.setattr(transcription, "VIDEO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS", 0)

    transcription.transcribe_video("video.mp4", 45, video_duration=1801)

    assert ranges == [(0, 30), (30, 45)]


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
