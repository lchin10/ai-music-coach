# AI Music Coach — Backend

FastAPI server handling sheet music detection, PDF→MusicXML conversion, multi-agent practice
plan generation, and the practice session runtime.

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
| `DATABASE_URL` | No | Direct Postgres connection string. Not used at runtime — handy for applying `migrations/*.sql` or `schema.sql` from the command line. |

## Database schema

**[`schema.sql`](schema.sql) is the full picture** — every table, column, index, RLS
policy and storage bucket, dumped from the live database with notes on what each
field is for. Read that first.

Two other things keep the schema honest:

- **`migrations/*.sql`** — run in the Supabase SQL editor, in order. Each one is
  additive and safe to re-run.
- **`app/schema.py`** — the columns the backend expects. `GET /sheet_music/schema`
  probes them and reports drift, so a forgotten migration fails loudly on startup
  instead of at insert time. Add new columns here *before* writing the migration.

| Migration | Adds |
|---|---|
| `001_planning_graph.sql` | `pieces.processing_stage`; `plan_steps` focus range, success criterion, `source` |
| `002_notation.sql` | `pieces.musicxml_path`, `pieces.measure_offset` |
| `003_storage_mime.sql` | Widens the `pieces` bucket MIME list; 25 MB limit |
| `004_storage_read_policy.sql` | The missing SELECT policy on `storage.objects` |
| `005_page_images.sql` | `pieces.page_images` (cropped staff systems) |
| `006_plan_quality.sql` | `pieces.plan_quality`; drops the LangGraph checkpoint tables |
| `007_practice_runtime.sql` | `practice_sessions`, `step_attempts`, `section_mastery`; `plan_steps.stage`/`.metronome` |
| `008_piece_identity.sql` | `pieces.work_title`, `pieces.composer` |

> **The load-bearing invariant:** sections belong to the *piece*, never to a plan
> version. Every ladder key and mastery row hangs off `section_id`, so
> regenerating sections with fresh UUIDs would orphan all practice history.
> `/sheet_music/retry` refuses once a piece has any recorded attempts.

> **CORS:** the server allows whichever of `FRONTEND_URL` / `FRONTEND_DEV_URL` are set (see `app/main.py`). Locally `.env.local` provides both, so `localhost:3000` and the deployed frontend both work. In production only `FRONTEND_URL` is set as a Fly secret, so only the Vercel origin is allowed.
>
> **Supabase key:** the backend falls back to the anon key if `SUPABASE_SERVICE_ROLE_KEY` is missing, but RLS policies will block inserts. Always use the service role key.

## Endpoints

### Score processing

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/sheet_music/schema` | Reports any expected table/column the database is missing |
| `POST` | `/sheet_music/detector` | Detects whether a PDF contains sheet music (OpenCV scoring) |
| `POST` | `/sheet_music/process` | Starts background processing: PDF → MusicXML → parse → AI plan → Supabase |
| `POST` | `/sheet_music/retry` | Re-runs processing from the stored PDF. Refuses if the piece has practice progress |
| `POST` | `/sheet_music/create_section` | **Dev only** — inserts a test section + practice plan for a given `piece_id` |

### Practice runtime

Only `/practice/struggling` can call a model, and only on a second tap. Everything
else is one round of queries plus arithmetic, because tapping "Nailed it" has to
advance instantly.

| Method | Path | Description |
|---|---|---|
| `POST` | `/practice/session/start` | Opens a session, returns the first action and the full rail |
| `GET` | `/practice/next` | The next thing to practise |
| `GET` | `/practice/step` | One rung in full, for jumping to it from the sidebar |
| `POST` | `/practice/attempt` | Records an attempt, updates mastery, returns the next action |
| `POST` | `/practice/skip_stage` | "I already know this" — clears a whole stage without inflating mastery |
| `POST` | `/practice/struggling` | Breaks the current rung down (deterministic first tap, agent on the second) |
| `POST` | `/practice/session/end` | Closes the session and banks the elapsed time |

## Layout

| Path | What lives there |
|---|---|
| `app/routers/sheet_music.py` | Upload, detection, processing, retry, schema check |
| `app/routers/practice.py` | The session runtime endpoints |
| `app/service/sheet_music_detector.py` | OpenCV scoring — is this actually sheet music? |
| `app/service/sheet_music_processor.py` | Audiveris → music21 → graph → Supabase |
| `app/service/page_crops.py` | Whitespace-gap detection to crop individual staff systems |
| `app/service/identify.py` | Normalises the piece's title and composer |
| `app/graph/` | The planning pipeline: `features`, `prompts`, `nodes`, `validate`, `build` |
| `app/coach/` | The practice runtime: `ladder`, `scheduler`, `remediate` |
| `app/schema.py` | Expected tables and columns, for the drift check |

## Processing pipeline

1. **Audiveris** converts the PDF to MusicXML (requires Audiveris installed; set `AUDIVERIS_PATH` if not on system PATH). Multi-movement splits are concatenated and renumbered.
2. **music21** parses it; `graph/features.py` builds a per-measure feature table — density, leaps, chord spans, hand crossing, polyrhythm, ornaments, plus repeat/volta/cadence structure.
3. **PyMuPDF** renders each page and `page_crops.py` slices out individual staff systems, so a drill can show exactly the bars it refers to. The PDF is the ground truth here, not the OMR: Audiveris drops fingerings, most dynamics, and notes on dense scores.
4. **The planning graph** (four Claude agents, `claude-opus-5`) segments, analyses, drills and reviews. Falls back to a deterministic equal-measure plan if it fails — marked `plan_quality = 'fallback'` so the UI can offer a retry rather than pretending.
5. Sections, plan and steps are written to Supabase; `status` becomes `"ready"`.

## The agents

Six Claude calls in total, all direct Anthropic SDK with forced tool use — LangGraph
orchestrates, it does not wrap the model, which keeps adaptive thinking, effort
levels, `cache_control` and `strict: true` tools available.

| Agent | Where | When | Effort |
|---|---|---|---|
| `define_sections` | `graph/prompts.py` | Once per piece | high |
| `analyze_section` | `graph/prompts.py` | Once per section (parallel) | high |
| `design_drills` | `graph/prompts.py` | Once per section (parallel) | high |
| `review_plan` | `graph/prompts.py` | Once, only if validation found problems | medium |
| `identify_piece` | `service/identify.py` | Once per piece | low |
| `prescribe_drills` | `coach/prompts.py` | Only on a second "Struggling" tap | low |

Everything else — segmentation features, the practice ladder, the scheduler,
mastery and decay, integration drills, first-tap remediation — is deterministic
Python. Teaching should be the same every time, and it's free.

## The practice ladder

`app/coach/ladder.py` turns a section into the progression a teacher would actually
use, and `app/coach/scheduler.py` decides which rung comes next.

```
notes       1-2 bar chunks, learn the notes        metronome OFF
thread      join them into a line                  metronome OFF
rhythm      only where the writing is awkward      metronome REQUIRED  <- first use
technique   isolate leaps and fast passagework     optional
transition  drill a seam, two beats if that's it   optional
pair        2 bars -> 4 -> 8 -> the whole section  optional
section     straight through, slowly               optional
tempo       three rungs, stopping at target        metronome REQUIRED
```

The metronome gate is a hard rule: you can't click to notes you don't have yet.

Rungs are **derived, never stored**. Each has a stable key
`{section_id}:{stage}:{start}-{end}`, and attempts are recorded against that — so
there is nothing to insert, nothing to renumber, and no drift between the plan and
what the student is practising. The ladder is built from `sections.analysis_data`,
which already exists, so no piece needs reprocessing.

Mastery is **capped by how far up the ladder you've climbed** (notes 25 · thread 40
· rhythm 55 · pair 70 · section 85 · tempo 100) and **decays** with
`mastery * exp(-days / (half_life * (1 + streak)))`. Review debt, revisiting and
joining finished sections all fall out of that arithmetic rather than needing an
agent.

## Tests

```bash
cd backend
python tests/test_graph.py       # validator, reducer and serialisation invariants
python tests/test_graph_flow.py  # the full graph against a stubbed model
python tests/test_ladder.py      # ladder, scheduler, mastery, decay, remediation
```

All three run offline and spend no tokens.

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
