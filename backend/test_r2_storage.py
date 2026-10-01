from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from app.services.r2_storage import CloudflareR2StorageBackend
from app.services.storage import StorageError, StorageObjectNotFound


class FakeR2Client:
    def __init__(self):
        self.objects = {}

    def upload_fileobj(self, source, bucket, key, ExtraArgs, Config):
        chunks = []
        while chunk := source.read(3):
            chunks.append(chunk)
        self.objects[(bucket, key)] = b"".join(chunks)
        self.extra_args = ExtraArgs
        self.transfer_config = Config

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey", "Message": "missing"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "HeadObject",
            )
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def download_file(self, bucket, key, filename, Config):
        Path(filename).write_bytes(self.objects[(bucket, key)])

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


def _backend(tmp_path):
    client = FakeR2Client()
    backend = CloudflareR2StorageBackend(
        client,
        "private-bucket",
        tmp_path / "uploads",
        tmp_path / "frames",
    )
    return backend, client


def test_r2_upload_streams_and_returns_only_object_key(tmp_path):
    from io import BytesIO

    backend, client = _backend(tmp_path)
    key = "videos/test/source.mp4"

    reference = backend.save_stream(BytesIO(b"video-content"), key)

    assert reference == key
    assert not Path(reference).is_absolute()
    assert client.objects[("private-bucket", key)] == b"video-content"
    assert client.extra_args["ContentType"] == "video/mp4"
    assert client.transfer_config.use_threads is False


def test_r2_materialize_downloads_to_temporary_file_and_cleans_it(tmp_path):
    from io import BytesIO

    backend, client = _backend(tmp_path)
    key = "videos/test/source.mp4"
    backend.save_stream(BytesIO(b"video-content"), key)

    with backend.materialize(key) as local_path:
        materialized = Path(local_path)
        assert materialized.is_file()
        assert materialized.read_bytes() == b"video-content"
        assert materialized != tmp_path / "uploads" / key

    assert not materialized.exists()


def test_r2_missing_object_uses_safe_reupload_error(tmp_path):
    backend, _ = _backend(tmp_path)

    assert backend.exists("videos/missing/source.mp4") is False
    with pytest.raises(StorageObjectNotFound) as error:
        with backend.materialize("videos/missing/source.mp4"):
            pytest.fail("missing object must not materialize")

    assert str(error.value) == (
        "The uploaded video is no longer available. Please upload the video again."
    )


def test_r2_delete_removes_object_and_invalid_keys_are_safe(tmp_path):
    from io import BytesIO

    backend, client = _backend(tmp_path)
    key = "videos/test/source.mp4"
    backend.save_stream(BytesIO(b"video"), key)

    backend.delete(key)

    assert not backend.exists(key)
    with pytest.raises(StorageObjectNotFound):
        with backend.materialize("C:/server/private/source.mp4"):
            pass
    with pytest.raises(StorageError, match="Invalid stored video reference"):
        backend.delete("../outside.mp4")


def test_r2_frame_workspace_remains_local(tmp_path):
    backend, _ = _backend(tmp_path)

    with backend.frame_workspace(37) as frames_root:
        assert Path(frames_root) == (tmp_path / "frames").resolve()
        assert (Path(frames_root) / "37").is_dir()


def test_r2_configuration_errors_do_not_echo_credentials(tmp_path):
    with pytest.raises(StorageError) as error:
        CloudflareR2StorageBackend.from_config(
            upload_dir=tmp_path / "uploads",
            frames_dir=tmp_path / "frames",
            account_id="account",
            access_key_id="access",
            secret_access_key="",
            bucket_name="bucket",
        )

    assert str(error.value) == (
        "R2 storage is selected but required environment configuration is missing."
    )


def test_video_storage_factory_keeps_local_default(monkeypatch):
    from app import config
    from app.services import storage

    local_backend = object()
    monkeypatch.setattr(config, "VIDEO_STORAGE_BACKEND", "local")
    monkeypatch.setattr(storage, "_video_storage", None)
    monkeypatch.setattr(storage, "get_local_storage", lambda: local_backend)

    assert storage.get_video_storage() is local_backend


def test_video_storage_factory_selects_configured_r2(monkeypatch):
    from app import config
    from app.services import r2_storage, storage

    r2_backend = object()
    captured = {}

    def build_backend(cls, **kwargs):
        captured.update(kwargs)
        return r2_backend

    monkeypatch.setattr(config, "VIDEO_STORAGE_BACKEND", "r2")
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "account-id")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "access-key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret-key")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "private-bucket")
    monkeypatch.setattr(storage, "_video_storage", None)
    monkeypatch.setattr(
        r2_storage.CloudflareR2StorageBackend,
        "from_config",
        classmethod(build_backend),
    )

    assert storage.get_video_storage() is r2_backend
    assert captured["account_id"] == "account-id"
    assert captured["bucket_name"] == "private-bucket"
