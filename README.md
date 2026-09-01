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
- **Practice Tracker**: Tracks time spent practicing and sections worked on.
- **Progress Memory**: Resume practice sessions without losing progress.

### Planned Features
- **Real-Time Feedback**: Microphone integration for live feedback on timing, notes, and technique.
- **Adaptive Practice Plans**: Dynamic recommendations that evolve based on user progress and weaknesses.
- **Difficulty Heatmaps**: Visual indicators of technically difficult sections.
- **Pattern Detection**: Detection of musical patterns (scales, arpeggios, jumps, polyrhythms) for tailored advice.
- **Library of Pieces**: Pre-built plans for popular piano pieces.

## Workflow

1. **Upload Sheet Music**: Upload a PDF containing piano sheet music.
2. **Score Analysis**: The backend analyzes the document using OpenCV-based notation detection and music analysis heuristics.
3. **Practice Plan Generation**: Receive a customized lesson plan with sections, tempo recommendations, and specific drills (e.g., "Practice measures 12–20 with left-hand jumps at 60 BPM").
4. **Practice Session**: Start a session, work through the plan, and track your progress.
5. **Resume Anytime**: Stop and restart sessions without losing progress.

## Technology Stack

- **Frontend**: Next.js 16, React 19, TypeScript, Tailwind CSS
- **Backend**: FastAPI, Python
- **AI**: Claude (Anthropic) API — four agents orchestrated with LangGraph (see [Practice plan pipeline](#practice-plan-pipeline))
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

### Tests

```bash
cd backend
python tests/test_graph.py       # validator + reducer invariants
python tests/test_graph_flow.py  # full graph with a stubbed model
```

Both run offline and spend no tokens.

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