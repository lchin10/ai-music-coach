# AI Music Coach — Backend

FastAPI server handling sheet music detection, PDF→MusicXML conversion, and AI-powered practice plan generation.

**Live API:** [ai-music-coach-api.fly.dev](https://ai-music-coach-api.fly.dev/) (Fly.io, Docker) — see [Deployment](#deployment).

## Setup

```bash
cd backend
pip install -e .                    # or: make install
cp .env.local.example .env.local   # fill in your values
make run                            # http://localhost:8000
```

Swagger UI / interactive docs: **http://localhost:8000/docs**

## Environment variables

Copy `.env.local.example` to `.env.local` and fill in all values.

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service role key — bypasses RLS for backend writes |
| `ANTHROPIC_API_KEY` | Yes | Claude API key for AI practice plan generation |
| `FRONTEND_URL` | Yes | Production CORS allowed origin (the Vercel URL) |
| `FRONTEND_DEV_URL` | No | Local CORS origin (e.g. `http://localhost:3000`); set in `.env.local` for local dev |
| `AUDIVERIS_PATH` | No | Full path to Audiveris executable if not on system PATH (set automatically in the Docker image) |

> **CORS:** the server allows whichever of `FRONTEND_URL` / `FRONTEND_DEV_URL` are set (see `app/main.py`). Locally `.env.local` provides both, so `localhost:3000` and the deployed frontend both work. In production only `FRONTEND_URL` is set as a Fly secret, so only the Vercel origin is allowed.
>
> **Supabase key:** the backend falls back to the anon key if `SUPABASE_SERVICE_ROLE_KEY` is missing, but RLS policies will block inserts. Always use the service role key.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/sheet_music/detector` | Detects whether a PDF contains sheet music (OpenCV scoring) |
| `POST` | `/sheet_music/process` | Starts background processing: PDF → MusicXML → parse → AI plan → Supabase |
| `POST` | `/sheet_music/create_section` | **Dev only** — inserts a test section + practice plan for a given `piece_id` |

## Processing pipeline

1. **Audiveris** converts the PDF to MusicXML (requires Audiveris installed; set `AUDIVERIS_PATH` if not on system PATH)
2. **music21** parses the MusicXML — extracts key, time signature, tempo, measure count, note density
3. **Claude API** (`claude-opus-4-8`) receives the musical context and returns a structured practice plan via forced tool use. Falls back to a heuristic plan if the API key is missing or the call fails.
4. Sections, practice plan, and plan steps are inserted into Supabase; piece `status` is updated to `"ready"`.

## External dependencies

- **Audiveris** — Java-based OMR tool for PDF→MusicXML. Install from [github.com/Audiveris/audiveris](https://github.com/Audiveris/audiveris/releases). On Windows the default install path `C:\Program Files\Audiveris\Audiveris.exe` is checked automatically if Audiveris is not on PATH. In Docker it is installed from the prebuilt Ubuntu `.deb` (see [Deployment](#deployment)).
- **Java** — required by Audiveris (JRE 17+). Bundled inside the Audiveris `.deb` in Docker, so no separate install is needed there.

## Deployment

Deployed to **Fly.io** as a Docker container (`Dockerfile` + `fly.toml`). A container is required because Audiveris is a system-level Java CLI that serverless hosts can't run, and processing is a long-running fire-and-forget background task.

The image (Ubuntu 22.04 base) installs Audiveris from the official prebuilt **`.deb`** (`Audiveris-5.10.2-ubuntu22.04-x86_64.deb`) rather than building from source — the source Gradle build fails because it pulls `javax.media.jai` from the now-defunct springsource repository. The `.deb` is jpackage-built and bundles its own JRE.

```bash
cd backend
fly apps create ai-music-coach-api            # once; name must be globally unique
Get-Content .env.local | fly secrets import    # push secrets (PowerShell); set FRONTEND_URL to the Vercel URL
fly deploy                                      # builds the Dockerfile and deploys
fly logs                                        # watch for OOM (exit 137) on large scores
```

Notes:
- `fly.toml` keeps the machine **always-on** (`auto_stop_machines = "off"`, `min_machines_running = 1`) so in-flight conversions survive idle traffic.
- Audiveris is memory-hungry; the default is 1 GB. If it OOMs, run `fly scale memory 2048`.
- Build/run the image locally with: `docker build -t amc-backend . && docker run --rm -p 8000:8000 --env-file .env.local amc-backend`.

## Scripts

```bash
make install   # pip install -e .
make run       # uvicorn with --reload, reads .env.local
make lint      # ruff .
make format    # black .
make clean     # remove build artifacts
```
