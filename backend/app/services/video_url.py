from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import yt_dlp

from ..config import UPLOAD_MAX_BYTES
from .video_source import detect_video_source


VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".m4v",
    ".mpeg",
    ".mpg",
}


class VideoTooLargeError(ValueError):
    """The URL video exceeded the configured upload byte limit."""


_YT_DLP_SIZE_LIMIT_MARKER = "VIDEOMIND_UPLOAD_SIZE_LIMIT_EXCEEDED"


def _extension_from_url(
    url: str,
) -> str:

    path = urlparse(url).path.lower()

    extension = Path(path).suffix

    if extension in VIDEO_EXTENSIONS:
        return extension

    return ".mp4"


def _download_direct_video(
    url: str,
    max_bytes: int,
) -> dict:
    extension = _extension_from_url(url)
    descriptor, filepath = tempfile.mkstemp(
        prefix="videomind-url-",
        suffix=extension,
    )
    os.close(descriptor)
    response = None
    succeeded = False

    try:
        response = requests.get(
            url,
            stream=True,
            timeout=60,
        )
        response.raise_for_status()

        content_type = (
            response.headers.get(
                "content-type",
                "",
            ).lower()
        )

        if (
            not content_type.startswith("video/")
            and extension not in VIDEO_EXTENSIONS
        ):
            raise ValueError(
                "The URL does not appear to point "
                "to a video file."
            )

        total_bytes = 0
        with open(filepath, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise VideoTooLargeError()
                output.write(chunk)

        succeeded = True
        return {
            "filepath": filepath,
            "title": Path(filepath).stem,
            "source_type": "direct",
        }
    finally:
        try:
            if response is not None:
                response.close()
        finally:
            if not succeeded:
                try:
                    os.remove(filepath)
                except FileNotFoundError:
                    pass


def _download_with_ytdlp(
    url: str,
    max_bytes: int,
) -> dict:
    if detect_video_source(url) == "youtube":
        raise ValueError("Use a supported YouTube URL for transcript analysis.")

    temporary_directory = tempfile.mkdtemp(prefix="videomind-ytdlp-")
    output_template = os.path.join(
        temporary_directory,
        "%(id)s.%(ext)s",
    )
    downloaded_sizes: dict[str, int] = {}

    def enforce_download_limit(progress: dict) -> None:
        filename = str(progress.get("filename", ""))
        downloaded_bytes = int(progress.get("downloaded_bytes") or 0)
        if filename:
            downloaded_sizes[filename] = max(
                downloaded_sizes.get(filename, 0),
                downloaded_bytes,
            )
        if sum(downloaded_sizes.values()) > max_bytes:
            raise yt_dlp.utils.DownloadError(_YT_DLP_SIZE_LIMIT_MARKER)

    options = {
        "quiet": True,
        "noplaylist": True,
        "outtmpl": output_template,
        "merge_output_format": "mp4",
        "max_filesize": max_bytes,
        "progress_hooks": [enforce_download_limit],
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            try:
                info = ydl.extract_info(url, download=True)
            except yt_dlp.utils.DownloadError as error:
                if _YT_DLP_SIZE_LIMIT_MARKER in str(error):
                    raise VideoTooLargeError() from error
                raise

        video_id = info.get("id")
        extension = info.get("ext") or "mp4"
        filepath = os.path.join(
            temporary_directory,
            f"{video_id}.{extension}",
        )

        if not os.path.isfile(filepath):
            candidates = [
                os.path.join(temporary_directory, name)
                for name in os.listdir(temporary_directory)
                if name.startswith(f"{video_id}.")
                and os.path.isfile(os.path.join(temporary_directory, name))
                and not name.endswith(".part")
            ]
            if candidates:
                filepath = candidates[0]

        if not os.path.isfile(filepath):
            raise ValueError("Video acquisition did not produce a video file.")
        if os.path.getsize(filepath) > max_bytes:
            raise VideoTooLargeError()

        return {
            "filepath": filepath,
            "temporary_directory": temporary_directory,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "fps": info.get("fps"),
            "width": info.get("width"),
            "height": info.get("height"),
            "source_type": detect_video_source(url),
            "external_id": video_id,
        }
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise


def acquire_video_from_url(
    url: str,
    max_bytes: int | None = None,
) -> dict:
    max_bytes = UPLOAD_MAX_BYTES if max_bytes is None else int(max_bytes)

    source_type = detect_video_source(
        url
    )

    if source_type == "youtube":
        raise ValueError("Use a supported YouTube URL for transcript analysis.")

    if source_type == "direct":
        return _download_direct_video(url, max_bytes)

    return _download_with_ytdlp(url, max_bytes)
