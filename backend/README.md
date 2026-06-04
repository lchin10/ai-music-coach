# AI Music Coach — Backend

FastAPI server handling sheet music detection, PDF→MusicXML conversion, and AI-powered practice plan generation.

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
| `FRONTEND_URL` | Yes | CORS allowed origin (e.g. `http://localhost:3000`) |
| `AUDIVERIS_PATH` | No | Full path to Audiveris executable if not on system PATH |

> **Note:** The backend falls back to the anon key if `SUPABASE_SERVICE_ROLE_KEY` is missing, but RLS policies will block inserts. Always use the service role key.

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

- **Audiveris** — Java-based OMR tool for PDF→MusicXML. Install from [github.com/Audiveris/audiveris](https://github.com/Audiveris/audiveris/releases). On Windows the default install path `C:\Program Files\Audiveris\Audiveris.exe` is checked automatically if Audiveris is not on PATH.
- **Java** — required by Audiveris (JRE 11+).

## Scripts

```bash
make install   # pip install -e .
make run       # uvicorn with --reload, reads .env.local
make lint      # ruff .
make format    # black .
make clean     # remove build artifacts
```
