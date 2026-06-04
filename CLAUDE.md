# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Frontend (`frontend/`)
```bash
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

### Backend (`backend/`)
```bash
make install     # pip install -e .
make run         # uvicorn with --reload, reads .env.local
make lint        # ruff .
make format      # black .
```
Backend API + docs at http://localhost:8000/docs.

## Architecture

This is a **Next.js frontend + FastAPI backend** app where Supabase acts as the shared auth/storage/database layer. The two servers run independently and communicate via HTTP; the backend URL is hardcoded to `http://localhost:8000` in the frontend upload page.

### Data flow: sheet music upload
1. **Frontend** (`upload/page.tsx`) — user drags in a PDF
2. Call `POST /sheet_music/detector` (multipart) → backend returns `{sheet_music: bool}` using OpenCV scoring
3. Upload PDF to **Supabase Storage** (`pieces` bucket) directly from the browser
4. Insert a `pieces` row in **Supabase DB** with `status: "processing"`
5. Fire-and-forget call to `POST /sheet_music/process` — backend runs the processing in a `BackgroundTask` and returns immediately
6. Frontend redirects to `/upload-confirmation`; plan is available once backend writes `status: "ready"`

### Backend processing pipeline (`service/sheet_music_processor.py`)
- Downloads the PDF from Supabase storage
- Runs **Audiveris** (system CLI tool) to convert PDF → MusicXML
- Parses MusicXML with **music21** to extract measures and notes
- Splits the piece into 3–5 sections; estimates difficulty per section (1–5 scale based on avg notes/measure)
- Writes `sections`, `practice_plans`, and `plan_steps` rows to Supabase
- Updates the `pieces` row to `status: "ready"` (or `"failed"`)

### OpenCV detection (`service/sheet_music_detector.py`)
Scores each PDF page by detecting: staff line groups (Canny + HoughLinesP), bar lines (vertical Hough), and note blobs (SimpleBlobDetector). A page needs a composite score ≥ 3 to be considered valid sheet music.

### Frontend auth pattern
`src/lib/userSession.ts` exposes a `useSession()` hook that wraps Supabase's `onAuthStateChange`. `src/lib/auth.ts` handles Google OAuth and post-auth routing (checks `profiles` table for onboarding completion).

## Environment variables

Both services need a `.env.local` file. Required keys:

| Key | Used by |
|-----|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | Frontend + backend |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Frontend |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend (bypasses RLS) |
| `FRONTEND_URL` | Backend CORS config |
| `DATABASE_URL` | Backend direct DB access |

## Key constraints

- **Audiveris must be installed** on the system for PDF→MusicXML conversion. Without it, `sheet_music_processor.py` will catch the `FileNotFoundError` and mark the piece as `"failed"`.
- The backend uses FastAPI `BackgroundTasks` — the process endpoint is intentionally fire-and-forget. Do not make it synchronous.
- Supabase CRUD for pieces/sections/plans lives **only in the backend** (not in Next.js API routes). The frontend reads from Supabase directly but writes only via the FastAPI backend.
