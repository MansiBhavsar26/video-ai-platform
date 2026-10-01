# VideoMind Backend

## Early access endpoint

URL:

```http
POST /api/early-access
```

Request body:

```json
{
  "name": "Alice Johnson",
  "email": "alice@example.com"
}
```

Expected successful response:

```json
{
  "success": true,
  "message": "Early access registration received."
}
```

Duplicate-email response:

```json
{
  "success": true,
  "message": "This email is already registered for early access."
}
```

Validation errors return HTTP 422 automatically when:

- name is empty or whitespace-only
- name length is less than 2 or greater than 100 characters
- email is invalid or empty

Local testing command:

```bash
cd backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Example request with curl:

```bash
curl -X POST http://localhost:8000/api/early-access \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice Johnson","email":"alice@example.com"}'
```

Example request with PowerShell:

```powershell
$body = '{"name":"Alice Johnson","email":"alice@example.com"}'
Invoke-RestMethod -Uri 'http://localhost:8000/api/early-access' -Method Post -ContentType 'application/json' -Body $body
```

## Production Deployment

Run the backend from the `backend/` directory. The deployment environment must
provide a PostgreSQL connection string and may override the other settings:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/video_ai
CORS_ORIGINS=https://videomind.in,http://localhost:5173
PORT=8000
SUPADATA_API_KEY=your-server-side-provider-key
```

`SUPADATA_API_KEY` configures the server-side YouTube transcript provider. It
does not contain YouTube account credentials or cookies. When it is absent,
local development falls back to `youtube-transcript-api`; production should
configure the provider key because cloud-provider IPs may be blocked by
YouTube. Optional settings include `SUPADATA_TIMEOUT_SECONDS`, `UPLOAD_DIR`,
`FRAMES_DIR`, `UPLOAD_MAX_BYTES`, `TESSERACT_PATH`, `YOLO_MODEL_PATH`, and the existing smart-sampling settings. `TESSERACT_PATH`
should be omitted when the `tesseract` executable is on the Linux `PATH`.

Install the backend dependencies with:

```bash
python -m pip install -r requirements.txt
```

Start the service with the platform-provided port:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

On PowerShell, use `--port $env:PORT`. The service exposes `GET /health`,
which returns `{"status":"ok","database":"ok"}` when the database is
reachable, and `GET /docs` for the OpenAPI documentation.

The application uses SQLAlchemy with PostgreSQL and calls
`Base.metadata.create_all()` during startup. This creates missing tables without
dropping existing tables or data. There is currently no migration system, so
schema changes will require a future migration process.

For verification, check `/health`, `/docs`, `POST /api/early-access`, a YouTube
analysis request, and `GET /videos/{id}/steps`. Set `CORS_ORIGINS` to a
comma-separated list of exact allowed origins; do not use `*` in production.

Full uploaded-video analysis requires OpenCV and the configured Faster-Whisper
model. YOLO uses the lightweight `yolo11n.pt` weights. If the configured file is
missing and its filename is `yolo11n.pt`, the backend downloads that specific
Ultralytics asset into the configured file's parent directory on first use and
reuses it for the rest of that running instance. Other missing custom model
files fail safely; they are not downloaded. The Render filesystem is
ephemeral, so the YOLO weights may need to be downloaded again after a restart
or instance replacement. No weight file is committed to Git.

OCR is optional enrichment. If Tesseract is installed and available on `PATH`,
OCR runs normally. On Linux deployments, install the OS-level Tesseract
executable in the service image/build environment; `pytesseract` alone is only
the Python wrapper. Set `TESSERACT_PATH` only when the executable is not on
`PATH`. If the executable is absent or OCR fails, the backend skips OCR and
continues analysis without OCR-derived evidence. This repository has no
Render build configuration that installs Tesseract automatically.

### Temporary video and frame storage

Uploaded source videos are stored on the backend's local filesystem under
`UPLOAD_DIR`; extracted frames are stored under `FRAMES_DIR`. Both paths are
configurable with environment variables and use platform-native path handling.
For local development, relative paths resolve from the backend process's
working directory:

```dotenv
UPLOAD_DIR=./uploads
FRAMES_DIR=./frames
UPLOAD_MAX_BYTES=209715200
```

The defaults are `backend/uploads` and `backend/frames`. The source video stays
on disk after analysis so it can be analyzed again. Frames are intermediate
analysis files; persistent transcripts, detections, evidence, and tutorial
steps are stored in PostgreSQL. The database health endpoint checks database
and application health, and does not require media directories to contain
files.

Render Free uses an ephemeral service filesystem and does not provide a
persistent disk. Videos and extracted frames are temporary there and may be
removed after a restart, redeploy, or instance replacement. PostgreSQL results
remain persistent, but if a source video has disappeared, users must upload it
again to rerun its video analysis. The analyze endpoint returns a safe
application error asking the user to upload the video again; it does not return
a server filesystem path or Python traceback. This MVP does not provide
persistent uploaded-media storage on Render Free.

The transcript-based YouTube guide pipeline continues to use its existing
transcript provider and does not require locally uploaded media.

Do not commit `.env` files, credentials, generated media, frames, or model
weights. Configure `VITE_API_BASE_URL` in the frontend deployment with the
public backend URL, for example `https://YOUR-BACKEND-DOMAIN`.

## Local video uploads

`ENABLE_OBJECT_DETECTION` controls optional YOLO analysis and defaults to
`true` to preserve local-development behavior. Set it to `false` to skip YOLO
and avoid importing Ultralytics/PyTorch during the request. Transcription,
sampled-frame OCR, developer-action extraction, evidence, and tutorial-step
generation continue; when YOLO is disabled, OCR uses its periodic sampled-frame
fallback without detector-based screen selection.

The app accepts `.mp4`, `.mov`, `.webm`, and `.mkv` uploads. MP4 is the recommended format. `POST /videos/upload` accepts multipart form data in the `file` field, checks the media type, extension, empty-file condition, and configured limits before saving to the local filesystem under `UPLOAD_DIR`. Non-YouTube media acquired through `POST /videos/url` uses the same byte and duration limits; YouTube continues through its transcript-only path. `UPLOAD_MAX_BYTES` sets the limit in bytes and defaults to 200 MiB. `VIDEO_ANALYSIS_MAX_DURATION_SECONDS` defaults to 1800 seconds (30 minutes). Files exceeding either limit are rejected before a persistent upload is created. The endpoint returns the created video ID and safe metadata, not its storage path.

Analysis uses bounded inputs for the Render Free 512 MB plan, but actual Render RSS must still be verified with a deployed run. `VIDEO_TRANSCRIPTION_CHUNK_SECONDS` defaults to 30 seconds and is capped at 30; `VIDEO_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS` defaults to 2 seconds and is capped at 5. Audio is decoded into one temporary chunk at a time; this bounds audio and feature extraction by chunk duration instead of full-video duration. Whisper runs before visual analysis and is released before YOLO weights load. `VIDEO_ANALYSIS_MAX_FRAMES` defaults to 30 sampled frames, `VIDEO_ANALYSIS_FRAME_ANALYSIS_INTERVAL_SECONDS` defaults to 10 seconds, and `VIDEO_ANALYSIS_MAX_FRAME_DIMENSION` defaults to 1280 pixels. OCR runs on likely screen/device frames and every third sampled frame as a fallback. YOLO uses `yolo11n.pt` and limits detections per frame. Generated frames are cleaned after analysis, including failed jobs where the process remains alive. The original uploaded source is retained.

Start processing with `POST /videos/{video_id}/analyze`, then poll `GET /videos/{video_id}/status` until the status is `completed` or `failed`. Completed guides are available at `GET /videos/{video_id}/steps`. Upload analysis uses faster-whisper and the existing visual analysis services. Local development needs FFmpeg and writable upload/frame storage. On Render Free, both source videos and extracted frames use the ephemeral service filesystem and can disappear after restart or redeploy. If a source is gone, status reports that it must be uploaded again; no persistent media service is configured by this MVP. PostgreSQL tutorial results remain stored.

`VideoEvidence` rows currently come from cleaned OCR text found in sampled
frames. They may be empty when the video has no legible screen text or OCR
filters all detections. Tutorial steps keep their transcript evidence on the
step records separately. In the recent 144p React tutorial excerpt run, the
analysis completed with transcript-backed steps but no cleaned OCR evidence, so
zero `VideoEvidence` records were expected for that run; this does not mean the
transcript or tutorial-step pipeline failed.

## Tests and production smoke test

Run the backend suite from `backend/` with `python -m pytest -q` and compile
checks with `python -m compileall app`. The frontend checks are `npm run lint`
and `npm run build` from `frontend/`. Follow
[PRODUCTION_SMOKE_TEST.md](PRODUCTION_SMOKE_TEST.md) for one manual production
check of health, YouTube transcript analysis, local upload, status, and steps.

Render Free has a 512 MB memory ceiling. Transcription is processed in bounded
chunks before visual analysis, and sampled frames are limited, but these code
limits do not guarantee that the deployed process will stay below the ceiling.
Observe Render Events and memory use during a short-video deployment check;
local success does not prove Render memory stability.
