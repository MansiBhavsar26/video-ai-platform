# VideoMind

VideoMind turns coding tutorials into timestamped implementation guides with
commands, file actions, transcript evidence, and confidence. It supports
YouTube transcript analysis and local video upload.

## Run locally

1. Set `DATABASE_URL` to a PostgreSQL database in the backend environment.
2. Install backend dependencies from `backend/requirements.txt` and start
   `uvicorn app.main:app --reload` from `backend/`.
3. Set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `frontend/.env`.
4. Run `npm install` and `npm run dev` from `frontend/`; open
   `http://localhost:5173/app`.

The backend also uses `SUPADATA_API_KEY` for the configured YouTube transcript
provider. See [backend setup and configuration](backend/README.md) and
[frontend setup](frontend/README.md) for details.

## Verify

Run backend tests with `python -m pytest -q` and syntax checks with
`python -m compileall app` from `backend/`. Run `npm run lint` and
`npm run build` from `frontend/`.

For a manual, one-video production check, follow
[PRODUCTION_SMOKE_TEST.md](backend/PRODUCTION_SMOKE_TEST.md).

## Deployment limitations

The current Render Free backend uses 512 MB RAM and ephemeral local storage.
Whisper audio processing uses bounded 30-second chunks; visual analysis is
limited to sampled frames. These bounds reduce peak allocations but do not
prove the deployed service stays below Render's memory limit. Verify RSS during
a real Render analysis. Uploaded source video can disappear after restart;
interrupted local-video analysis may then require a re-upload. Database-stored
transcripts and guides remain available.

The frontend is deployed separately on Vercel. Set its public
`VITE_API_BASE_URL` to the backend URL. Never put backend secrets in frontend
variables.
