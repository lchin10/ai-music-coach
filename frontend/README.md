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
| `NEXT_PUBLIC_BACKEND_URL` | Base URL of the FastAPI backend (e.g. `http://localhost:8000` in dev, or the deployed Render URL). Optional in dev — defaults to `http://localhost:8000`. |

## Key pages

| Route | Description |
|---|---|
| `/` | Landing page |
| `/signup` `/signin` | Auth (Google OAuth via Supabase) |
| `/onboarding` | Piano level + experience form (first login) |
| `/upload` | Drag-and-drop PDF upload; detects sheet music, uploads to Supabase Storage, triggers backend processing |
| `/upload-confirmation` | Post-upload holding page |
| `/profile` | Lists all uploaded pieces with status; ready pieces are clickable |
| `/piece/[id]` | Practice plan for a piece — sections, difficulty, and ordered drill steps |

## Architecture notes

- **Auth** — Supabase Google OAuth. `src/lib/userSession.ts` exposes `useSession()` wrapping `onAuthStateChange`. `src/lib/auth.ts` handles post-auth routing and checks `profiles` for onboarding completion.
- **Upload flow** — frontend calls `POST /sheet_music/detector` (backend) to validate the PDF, then uploads directly to Supabase Storage (`pieces` bucket), inserts a `pieces` row with `status: "processing"`, then fires `POST /sheet_music/process` (fire-and-forget). The piece becomes clickable once the backend sets `status: "ready"`.
- **Supabase reads** — the frontend reads `pieces`, `sections`, `practice_plans`, and `plan_steps` directly. All writes to those tables go through the backend.

## Scripts

```bash
npm run dev      # dev server with hot reload
npm run build    # production build
npm run lint     # ESLint
```
