-- Phase 4: the practice session runtime.
-- Run in the Supabase SQL editor before deploying — /practice/* writes these
-- tables and every insert fails without them.

-- Remediation drills are the ONE thing the runtime persists — they're model
-- output, so losing them on a reload would mean paying twice. They ride in
-- plan_steps on the `source` column migration 001 already added, and need the
-- two fields a ladder step carries that an authored drill doesn't.
alter table plan_steps
  add column if not exists stage      text,
  add column if not exists metronome  text;

create table if not exists practice_sessions (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  piece_id uuid not null references pieces(id) on delete cascade,
  started_at timestamptz default now(),
  ended_at timestamptz,
  total_seconds int default 0
);

-- An earlier schema already created practice_sessions (id, user_id, piece_id,
-- started_at, ended_at, notes), and `create table if not exists` above is a
-- no-op against it — so add the column explicitly or the session-end write
-- fails on a database that looks fine.
alter table practice_sessions
  add column if not exists total_seconds int default 0;

-- step_key is a DERIVED ladder key ("<section_id>:pair:12-19") or the uuid of
-- a remediation plan_steps row. Ladder steps are computed from the section on
-- every request and never stored, so there is no row to point an FK at — see
-- app/coach/ladder.py for why that's deliberate.
create table if not exists step_attempts (
  id uuid primary key,
  session_id uuid not null references practice_sessions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  section_id uuid not null references sections(id) on delete cascade,
  step_key text not null,
  stage text not null,
  created_at timestamptz default now(),
  seconds int default 0,
  tempo_reached int,
  metronome_on boolean default false,
  self_report text check (self_report in ('nailed','shaky','struggling')),
  skipped boolean default false,
  notes text
);

create table if not exists section_mastery (
  user_id uuid not null references auth.users(id) on delete cascade,
  section_id uuid not null references sections(id) on delete cascade,
  mastery int default 0,
  streak int default 0,
  times_reviewed int default 0,
  reached_stage text default 'notes',
  last_practiced_at timestamptz default now(),
  primary key (user_id, section_id)
);

create index if not exists step_attempts_key_idx on step_attempts (user_id, step_key);
create index if not exists step_attempts_section_idx on step_attempts (section_id);
create index if not exists practice_sessions_piece_idx on practice_sessions (user_id, piece_id);

-- The frontend reads progress directly; all writes go through the backend on
-- the service role, which bypasses RLS.
alter table practice_sessions enable row level security;
alter table step_attempts     enable row level security;
alter table section_mastery   enable row level security;

drop policy if exists "own practice sessions" on practice_sessions;
create policy "own practice sessions" on practice_sessions
  for select using (auth.uid() = user_id);

drop policy if exists "own step attempts" on step_attempts;
create policy "own step attempts" on step_attempts
  for select using (auth.uid() = user_id);

drop policy if exists "own section mastery" on section_mastery;
create policy "own section mastery" on section_mastery
  for select using (auth.uid() = user_id);

-- INVARIANT, continued from migration 001: mastery and every ladder key hang
-- off section_id. _persist deletes and recreates sections on each run, which
-- was harmless only while nothing referenced them. /sheet_music/retry now
-- refuses once a piece has attempts.
