# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Frontend (`frontend/`)
```bash
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
npm run test:e2e          # Playwright screenshots + flows (starts its own servers on :3100/:8100)
npm run test:e2e:update   # re-baseline after an intended UI change; say which pages and why
```

### Backend (`backend/`)
```bash
make install     # pip install -e .
make run         # uvicorn with --reload, reads .env.local
make dev         # pip install -e .[dev] (pytest, httpx)
make test        # python -m pytest -q, offline, no tokens
make lint        # ruff .
make format      # black .
```
Backend API + docs at http://localhost:8000/docs.

## Architecture

This is a **Next.js frontend + FastAPI backend** app where Supabase acts as the shared auth/storage/database layer. The two servers run independently and communicate via HTTP. Every frontend call to the backend goes through `backendFetch` (`src/lib/backend.ts`), which reads `NEXT_PUBLIC_BACKEND_URL` and attaches the user's Supabase access token.

### Data flow: sheet music upload
1. **Frontend** (`upload/page.tsx`) — user drags in a PDF
2. Call `POST /sheet_music/detector` (multipart, authenticated) → backend returns `{sheet_music: bool}` using OpenCV scoring
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
- Supabase CRUD for pieces/sections/plans lives **only in the backend** (not in Next.js API routes). The frontend reads from Supabase directly but writes only via the FastAPI backend. The one exception is the upload itself: the browser puts the PDF in Storage and inserts its `pieces` row under RLS.
- **Every backend endpoint except `GET /` requires a Bearer token.** The backend uses the service-role key (RLS bypassed), so `app/auth.py` is the access control: `Depends(current_user)` for identity, then `own_piece` / `own_session` for every id in the request. Never accept a `user_id` from the client. New endpoints get rows in `tests/test_auth.py`'s `ROUTES` table.
- **Tests run against production Supabase** only through the e2e test account (`frontend/e2e/fixture.ts`). Its writes and deletes are always filtered by that account's id. Never point the e2e suite at real users' data, and never seed through anything but `fixture.ts`.
- A Stop hook (`.claude/hooks/check.py`) runs the suites covering uncommitted changes and checks doc drift: new migration ⇒ `schema.sql` + `app/schema.py`; route change ⇒ `backend/README.md`; new page ⇒ `e2e/pages.spec.ts` (+ verify feature map). Failures go to `test-logs/<timestamp>/`.

## Workflow (pstack)

| Situation | Command |
|---|---|
| Feature or multi-file change | `/pstack:poteto-mode <goal>` (the pstack SessionStart hook routes these automatically) |
| Understand a subsystem | `/pstack:how` |
| Design choice | `/pstack:architect` |
| Contested design or risky diff | `/pstack:interrogate` |
| Bug with unknown cause | `/pstack:poteto-mode` → Bug fix playbook (reproduce first) |
| Before commit | `/pstack:deslop`, then the `security-review` skill |
| After the app changes | `/maintain-verification-skill` (keeps the verify feature map honest) |
| Week recap | `/pstack:what-did-i-get-done` |

The project playbook `.agents/playbooks/fullstack.md` adds this repo's test, security and docs steps to pstack's Feature and Bug fix playbooks, and replaces "open a PR" with a commit on the current branch.
