# AI Music Coach — Frontend

Next.js 15 (App Router) frontend. Communicates with the FastAPI backend at `http://localhost:8000` and reads/writes Supabase directly for auth and data.

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
