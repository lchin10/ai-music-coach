# AI Music Coach

**Live demo:** [ai-music-coach-eight.vercel.app](https://ai-music-coach-eight.vercel.app/) &nbsp;·&nbsp; **API:** [ai-music-coach-api.fly.dev](https://ai-music-coach-api.fly.dev/)

AI Music Coach is a web application designed to help musicians (especially pianists) practice more effectively through structured, AI-assisted practice planning. Users can upload sheet music PDFs, and the app analyzes the score using computer vision and music theory heuristics to generate personalized practice recommendations, section breakdowns, and targeted drills.

I built this project as someone who has played piano for ~15 years and minored in music performance. Outside of software, music has always been one of my favorite hobbies, and I wanted to create something for people who still want to grow as musicians even when music is no longer their full-time focus. The goal is to make practicing feel more organized, motivating, and sustainable for hobbyists and serious learners alike.

The app serves as both a practice planner and a progress tracker, allowing users to resume sessions seamlessly and build long-term consistency through data-driven insights.

## Features

### MVP Features
- **Sheet Music Upload**: Upload piano sheet music in PDF format.
- **Computer Vision-Based Score Detection**: Uses OpenCV-based music notation detection to validate and analyze uploaded sheet music
- **Multi-Agent Practice Planning**: A LangGraph pipeline of four Claude agents that read the actual score — not a summary of it — and generate:
  - Section breakdowns based on real musical structure (repeats, cadences, key changes)
  - Per-section technical analysis anchored to specific measures
  - Targeted drills (e.g., hands-separate practice, specific measure focus)
  - A reviewed, validated plan personalized to the player's level
- **Notation in context**: Every drill shows the actual bars it refers to, cropped from your PDF — plus the full score, always one click away.
- **Guided practice sessions**: A teacher's ladder, one rung at a time — learn the notes, thread them together, then rhythm, technique, seams, pairing up, and finally tempo (see [Practice session runtime](#practice-session-runtime)).
- **A metronome that stays locked** until the notes are learned, because you can't click to notes you don't have yet.
- **Honest progress**: Mastery is capped by how far up the ladder you've climbed and decays over time, so old sections resurface for review on their own.
- **"Struggling" actually does something**: The coach narrows the drill instantly, and diagnoses it properly if that isn't enough.

### Planned Features
- **Real-Time Feedback**: Microphone integration for live feedback on timing, notes, and technique.
- **Session recaps**: An end-of-session note and plan revisions based on what actually happened.
- **Audio recording**: Capture attempts for self-review.
- **Difficulty Heatmaps**: Visual indicators of technically difficult sections.
- **Library of Pieces**: Pre-built plans for popular piano pieces.

## Workflow

1. **Upload Sheet Music**: Upload a PDF containing piano sheet music.
2. **Score Analysis**: The backend analyzes the document using OpenCV-based notation detection and music analysis heuristics.
3. **Practice Plan Generation**: Four Claude agents produce a sectioned plan with per-section analysis, tempo targets and targeted drills (e.g., "Loop mm. 23–25, LH leap of a tenth into the m.24 downbeat, 60 BPM").
4. **Practice Session**: Work through the ladder one rung at a time, with the bars in front of you and a metronome when — and only when — you're ready for it. Report *nailed*, *shaky* or *struggling* on each.
5. **Resume Anytime**: The scheduler knows where you left off, what has gone stale, and when two sections are ready to be joined.

## Technology Stack

- **Frontend**: Next.js 16, React 19, TypeScript, Tailwind CSS
- **Backend**: FastAPI, Python
- **AI**: Claude (Anthropic) API, `claude-opus-5` — six agents, four of them orchestrated with LangGraph (see [Practice plan pipeline](#practice-plan-pipeline))
- **Music processing**: Audiveris (PDF → MusicXML OMR), music21
- **Computer Vision**: OpenCV, PyMuPDF, NumPy, Pillow
- **Auth / Data / Storage**: Supabase (Postgres, Storage, Google OAuth)
- **Deployment**: Vercel (frontend), Fly.io via Docker (backend)

## Practice plan pipeline

Uploading a PDF runs a LangGraph state machine in `backend/app/graph/`. Only the four
LLM nodes call Claude; everything else is deterministic Python, because music21 is
better and cheaper at reading a score than a model is.

```
ingest              Audiveris → MusicXML → music21
      ↓
extract_features    per-measure table: density, leaps, chord spans, hand crossing,
                    polyrhythm, ornaments, repeat/volta/cadence structure
      ↓
segment             [Claude] → N sections, bounded by real musical structure
      ↓
   ┌── one parallel branch per section ──┐
   │   analyze_section  [Claude]         │  challenges, techniques, risk measures
   │   design_drills    [Claude]         │  ordered steps, tempo ladder, focus ranges
   └─────────────────────────────────────┘
      ↓
validate            ~20 deterministic assertions → report
      ↓
critique            [Claude] approve or revise (max 2 rounds)
      ↓
persist             Supabase
```

**There is no fixed section count.** The segmenter is given a definition of what a
section is — a practice-sized, musically coherent unit bounded by repeats, double
barlines, key changes or cadences — and lets the music decide. A 16-measure minuet
yields 1–2 sections; a long sonata movement yields 15–25.

**Cost guards**, cheapest first:

| Guard | Where | Limit |
|---|---|---|
| Page count | `sheet_music_detector.py` (before any rendering) | 20 pages |
| File size | `routers/sheet_music.py` | 25 MB |
| Measure count | `graph/features.py`, before the fan-out | 400 measures |
| Section fan-out | `graph/nodes.py` | 30 sections |

The fan-out is where the money goes — N sections means 2N calls — so all N branches
share one cached prefix (`cache_control` on the system prompt and the feature table).
Check `cache_read_input_tokens` in the logs; if it's zero on branches 2..N, something
volatile leaked into the prefix.

If the graph fails for any reason, `_fallback_plan` writes a deterministic plan rather
than failing the piece — a mediocre plan beats `status: "failed"`.

### The other two agents

Not every model call belongs in the graph:

- **`identify_piece`** (`service/identify.py`) — a scanned PDF has no text layer, and Audiveris' OCR of the title block produces things like `S. RACHMANINOFF, 0p. 3. Na. 2`. Those errors differ every scan, so a regex can't fix them. One cheap call reconciles the OCR with the filename into *Prelude in C-sharp minor, Op. 3 No. 2 — Sergei Rachmaninoff (arr. Leopold Godowsky)*.
- **`prescribe_drills`** (`coach/prompts.py`) — the remediation agent, described below.

## Practice session runtime

The plan is only half the app. The other half is practising it, and the naive
version — walk the drill list and tick boxes — is not how anyone learns a piece
with a teacher. The real progression inside a section is a **ladder**:

```
notes       1-2 bar chunks, learn the notes           metronome OFF
thread      join them into a line, free tempo         metronome OFF
rhythm      only where the writing is awkward         metronome REQUIRED  <- first use
technique   isolate leaps and fast passagework        optional
transition  drill a seam — two beats, if that's it    optional
pair        2 bars -> 4 -> 8 -> the whole section     optional
section     straight through, slowly                  optional
tempo       three rungs, stopping at target           metronome REQUIRED
```

Above that, the scheduler joins adjacent finished sections and brings back ones
that have gone stale.

**The ladder is derived, not generated.** Its shape is the same for every section
— that's what makes it teaching rather than improvisation — so it's plain Python
built from data the analysis agent already produced (`risk_measures`,
`techniques`, `tempo_floor`, `tempo_target`). No model call, no prompt, and no
piece needs reprocessing. Rungs are computed on request and never stored; each
has a stable key so progress can't orphan.

Three rules do the real work:

- **The metronome is locked** through `notes` and `thread`. You can't click to
  notes you don't have yet, and a student left alone reaches for it far too early.
- **Mastery is capped by the ladder** — notes 25 · thread 40 · rhythm 55 ·
  pair 70 · section 85 · tempo 100. You cannot read 90% on a passage you have
  only ever played two bars at a time.
- **Mastery decays**, with a half-life that grows as your streak does. Review debt
  and revisiting fall out of the arithmetic instead of needing an agent.

**When a rung isn't working**, the first "Struggling" tap narrows it in Python —
free and instant, and the ladder always has a rung below (a failing `pair` becomes
its seam; a failing `transition` becomes landing on the downbeat from a dead stop).
Only a *second* tap on the same rung pays for `prescribe_drills`, which diagnoses
why this passage is failing and prescribes a different angle. If that call fails or
returns anything that doesn't validate, it falls back to the deterministic
narrowing — an optional agent must never dead-end a session.

## Data schema

**[`backend/schema.sql`](backend/schema.sql)** is the full data model: every table,
column, index, RLS policy and storage bucket, with notes on what each field is for.

Two other pieces keep it honest — `backend/migrations/*.sql` (run in order in the
Supabase SQL editor) and `backend/app/schema.py`, the columns the backend expects.
`GET /sheet_music/schema` probes the live database against that list, so a
forgotten migration fails loudly instead of at insert time.

The frontend reads these tables directly under RLS; every write goes through the
backend on the service-role key.

### Tests

```bash
cd backend
python tests/test_graph.py       # validator, reducer and serialisation invariants
python tests/test_graph_flow.py  # full graph with a stubbed model
python tests/test_ladder.py      # ladder, scheduler, mastery, decay, remediation
```

All three run offline and spend no tokens.

## Requirements

- Node.js 18+
- Python 3.10+
- npm or yarn for package management
- A modern web browser with JavaScript enabled

## Installation and Setup

**Clone the Repository**:
  ```bash
  git clone https://github.com/yourusername/ai-music-coach.git
  cd ai-music-coach
  ```

**Frontend Setup**:
  Navigate to the frontend directory and install packages:
  ```bash
  cd frontend
  npm install
  npm run dev
  ```
  Frontend runs at [http://localhost:3000](http://localhost:3000)

**Backend Setup**:
  ```bash
  cd backend
  make install
  make run
  ```
  Backend runs at [http://localhost:8000/docs](http://localhost:8000/docs)

4. **Build for Production**:
   ```bash
   npm run build
   npm start
   ```

## Deployment

The frontend and backend deploy independently; Supabase is the shared auth/storage/database layer for both.

| Service | Host | Source | Live URL |
|---|---|---|---|
| Frontend (Next.js) | Vercel | root dir `frontend/` | [ai-music-coach-eight.vercel.app](https://ai-music-coach-eight.vercel.app/) |
| Backend (FastAPI) | Fly.io (Docker) | `backend/Dockerfile` + `backend/fly.toml` | [ai-music-coach-api.fly.dev](https://ai-music-coach-api.fly.dev/) |

### Frontend → Vercel
- Import the repo into Vercel with **Root Directory = `frontend/`** (Next.js is auto-detected).
- Set env vars: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `NEXT_PUBLIC_BACKEND_URL` (the Fly API URL).
- Add the Vercel domain to **Supabase → Auth → URL Configuration** so Google OAuth redirects resolve.

### Backend → Fly.io
The backend ships as a Docker image because it needs **Audiveris** (a Java OMR CLI) installed system-wide — which serverless platforms like Vercel can't provide. The image installs Audiveris from its prebuilt Ubuntu `.deb`, so no separate JRE or source build is required.

```bash
cd backend
fly apps create ai-music-coach-api          # once
Get-Content .env.local | fly secrets import  # push secrets (PowerShell)
fly deploy                                    # builds Dockerfile, deploys
```

The machine is configured always-on (`auto_stop_machines = "off"`, `min_machines_running = 1`) in [`fly.toml`](backend/fly.toml) because processing runs as a fire-and-forget background task that must survive idle traffic. If Audiveris runs out of memory on large scores, raise RAM with `fly scale memory 2048`. See [`backend/README.md`](backend/README.md) for env vars and details.

## Future Development

- More robust music notation detection
- Better section segmentation
- AI-generated fingering suggestions
- Real-time performance feedback
- Cloud-based accounts and sync
- Mobile support
- Expanded support for non-piano instruments