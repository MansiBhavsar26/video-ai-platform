# Production smoke test

This is a manual, one-item check of the deployed API. It makes no repeated
requests automatically and needs no API credential. Use a short, public,
transcript-enabled YouTube tutorial and a small local video that you are
permitted to upload. Render Free media storage is ephemeral, so an uploaded
source may need to be submitted again after a restart.

In PowerShell, set the public API base URL and check health:

```powershell
$api = 'https://video-ai-platform-l80h.onrender.com'
Invoke-RestMethod "$api/health"
```

Expected: `status` and `database` are both `ok`.

## YouTube transcript flow

The UI calls `POST /videos/youtube`; `POST /videos/url` also accepts YouTube
URLs. Both use transcript analysis and do not download the YouTube video. This
check exercises `/videos/url`:

```powershell
$youtubeUrl = Read-Host 'Paste a public transcript-enabled YouTube URL'
$encodedUrl = [uri]::EscapeDataString($youtubeUrl)
$youtube = Invoke-RestMethod -Method Post -Uri "$api/videos/url?url=$encodedUrl"
$youtube | Select-Object id, status, message
$youtubeId = $youtube.id
Invoke-RestMethod "$api/videos/$youtubeId/status"
Invoke-RestMethod "$api/videos/$youtubeId/steps"
```

The YouTube endpoint performs transcript analysis during the POST. A provider
or unavailable-transcript response is a valid smoke-test failure; use a
different public video with captions before concluding the deployment is
broken.

## Local video flow

Choose a small `.mp4`, `.mov`, `.webm`, or `.mkv` file. The default limit is
200 MiB and 30 minutes. The backend validates format, size, and duration.

```powershell
$videoPath = Read-Host 'Enter the full path to a small local test video'
$uploadJson = curl.exe --fail-with-body -sS -F "file=@$videoPath" "$api/videos/upload"
$upload = $uploadJson | ConvertFrom-Json
$upload | Select-Object id, status, duration
$videoId = $upload.id
Invoke-RestMethod -Method Post -Uri "$api/videos/$videoId/analyze"
```

Poll status manually every few seconds:

```powershell
Invoke-RestMethod "$api/videos/$videoId/status"
```

When status is `completed`, fetch the guide:

```powershell
Invoke-RestMethod "$api/videos/$videoId/steps"
```

If status is `failed`, the status response should give a safe user-facing
message. If it says the source video is no longer available, upload the file
again. Check Render Events for the analysis outcome and memory events. A
successful one-video run is useful operational evidence, but does not prove
every input fits within 512 MB RAM.
