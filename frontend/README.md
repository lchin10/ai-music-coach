# AI Music Coach — Frontend

Next.js 16 (App Router) frontend. Communicates with the FastAPI backend (at `NEXT_PUBLIC_BACKEND_URL`, defaulting to `http://localhost:8000` in dev) and reads/writes Supabase directly for auth and data.

**Live:** [ai-music-coach-eight.vercel.app](https://ai-music-coach-eight.vercel.app/) — deployed on Vercel. Backend API: [ai-music-coach-api.fly.dev](https://ai-music-coach-api.fly.dev/).

## Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local   # fill in your values
npm run dev                         # http://localhost:3000
```

## Environment variables

Copy `.env.local.example` to `.env.local` and fill in the values from your Supabase project (**Settings → API**).

| Variable | Where to find it |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase → Settings → API → Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase → Settings → API → anon / public key |
| `NEXT_PUBLIC_BACKEND_URL` | Base URL of the FastAPI backend (e.g. `http://localhost:8000` in dev, or the deployed Fly.io URL). Optional in dev — defaults to `http://localhost:8000`. |

## Key pages

| Route | Description |
|---|---|
| `/` | Landing page |
| `/signup` `/signin` | Auth (Google OAuth via Supabase) |
| `/onboarding` | Piano level + experience form (first login) |
| `/upload` | Drag-and-drop PDF upload; detects sheet music, uploads to Supabase Storage, triggers backend processing |
| `/upload-confirmation` | Post-upload holding page |
| `/profile` | Account details and the piece library — title, composer, upload date and the opening bars |
| `/piece/[id]` | The plan: title/composer, overall difficulty, opening bars, collapsed sections with per-section mastery, and the full PDF |
| `/practice/[pieceId]` | The session runtime — one rung at a time, with notation, metronome and feedback |

## Components and helpers

| File | Role |
|---|---|
| `components/ScorePages.tsx` | Shows the staff systems covering a measure range, cropped from the PDF |
| `components/FullScore.tsx` | The whole PDF, collapsed by default; signs its URL only when opened |
| `lib/metronome.ts` | Web Audio metronome |
| `lib/pieceName.ts` | Display title/composer, with a tidied filename as the fallback |
| `lib/userSession.ts` | `useSession()` over Supabase `onAuthStateChange` |

**Notation is cropped from the PDF, not re-rendered.** Audiveris drops fingerings,
most dynamics and — on dense scores — notes, so a re-render would show music that
doesn't match the page the user is playing from. The backend slices each staff
system at processing time and stores the crops in `pieces.page_images`; the
component signs and displays the ones overlapping the requested bars, on a white
panel because that's what engraved music is meant to be read on.

**The metronome uses a lookahead scheduler**, not `setInterval` — a ~25 ms timer
queues oscillators against `audioContext.currentTime` about 100 ms ahead. Timer
drift is audible within a minute, and a metronome that lies is worse than none on a
tempo-building drill.

## Architecture notes

- **Auth** — Supabase Google OAuth. `src/lib/userSession.ts` exposes `useSession()` wrapping `onAuthStateChange`. `src/lib/auth.ts` handles post-auth routing and checks `profiles` for onboarding completion.
- **Upload flow** — frontend calls `POST /sheet_music/detector` (backend) to validate the PDF, then uploads directly to Supabase Storage (`pieces` bucket), inserts a `pieces` row with `status: "processing"`, then fires `POST /sheet_music/process` (fire-and-forget). The piece becomes clickable once the backend sets `status: "ready"`.
- **Practice session** — `/practice/[pieceId]` is thin. It calls `POST /practice/session/start` and renders whatever comes back: the current rung, the sidebar rail, and per-section mastery. Every decision about *what to practise next* lives in the backend scheduler, so the page never has to model the ladder. Sessions close on `pagehide` via `navigator.sendBeacon`, since a normal `fetch` is killed on unload.
- **Supabase reads** — the frontend reads `pieces`, `sections`, `practice_plans`, `plan_steps` and `section_mastery` directly, under RLS. All writes go through the backend, which holds the service-role key. See [`backend/schema.sql`](../backend/schema.sql) for the full data model.

## Scripts

```bash
npm run dev      # dev server with hot reload
npm run build    # production build
npm run lint     # ESLint
```
