# VideoMind frontend

## Local setup

```bash
npm install
npm run dev
```

## Production build

```bash
npm run build
npm run preview -- --host 0.0.0.0
```

## Output directory

- Build output: `dist`

## Required public environment variable

Create a `.env` file from `.env.example` and set:

```bash
VITE_API_BASE_URL=https://your-public-api-domain.example
```

This value must be a public, non-secret base URL. Do not place backend credentials or private keys in VITE_ variables.

## Early-access backend endpoint

The early-access form expects a public backend route:

```http
POST /api/early-access
```

Request body:

```json
{
  "name": "string",
  "email": "string",
  "consent": true
}
```

The endpoint is implemented by the backend and returns JSON in the form:

```json
{
  "success": true,
  "message": "string"
}
```

or an error response:

```json
{
  "success": false,
  "message": "string"
}
```

The form submits the visitor's name and email to the backend. The consent
checkbox is part of the frontend flow; it is not currently persisted as a
separate database field.

## Deployment notes

- Domain: `https://videomind.in/`
- HTTPS is required for production usage.
- Ensure the Vite build output is served from the configured web host and that SPA fallback is enabled for routes such as `/privacy-policy`.
- Verify the favicon and the social preview image load correctly in production.
- Test the live site in an incognito browser session to confirm the route, metadata, and form state behave as expected.

## Verification checklist

- Confirm `/privacy-policy` loads correctly.
- Confirm `/og-image.svg` loads and the social preview renders properly.
- Confirm the favicon loads without 404s.
- Confirm the early-access form does not silently store submissions in browser localStorage for production.
- Confirm the site works correctly over HTTPS.

The `/app` analyzer accepts YouTube URLs and local `.mp4`, `.mov`, `.webm`, or `.mkv` files. The local upload limit defaults to 200 MiB. If the backend sets a different `UPLOAD_MAX_BYTES`, set the same byte value in the frontend build as `VITE_MAX_UPLOAD_BYTES` so browser validation matches the server. The backend also limits local uploads to 30 minutes by default (`VIDEO_ANALYSIS_MAX_DURATION_SECONDS`). For the production site, set `VITE_API_BASE_URL=https://video-ai-platform-l80h.onrender.com`; this is a public URL, not a secret.
