-- =============================================================================
-- AI Music Coach — full database schema
-- =============================================================================
--
-- This is the CURRENT state of the Supabase Postgres database, dumped from the
-- live instance. It is documentation and a from-scratch bootstrap, not part of
-- the migration sequence: an existing database is brought up to date by running
-- migrations/*.sql in order, and `GET /sheet_music/schema` reports any drift
-- against app/schema.py.
--
-- Ownership rule: the frontend READS these tables directly under RLS. Every
-- write goes through the FastAPI backend on the service-role key, which
-- bypasses RLS. That is why most tables have SELECT policies but no INSERT or
-- UPDATE policy for the newer tables.
--
-- Supabase provides auth.users; profiles.id is a 1:1 extension of it.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Types
-- -----------------------------------------------------------------------------

-- Mirrored in app/graph/prompts.py as DRILL_TYPES; the drill-designer agent is
-- enum-bound to it, so adding a value here means adding it there too.
create type drill_type_enum as enum (
  'hands_separate',
  'hands_together',
  'loop',
  'slow_practice',
  'tempo_building',
  'rhythm_variation',
  'metronome',
  'articulation_focus',
  'checkpoint'
);


-- =============================================================================
-- Identity
-- =============================================================================

-- 1:1 extension of auth.users. Written by the onboarding form; the planning
-- agents read piano_level and years_experience to pitch difficulty and tempo.
create table profiles (
  id                  uuid primary key references auth.users (id) on delete cascade,
  name                text,
  piano_level         text,          -- 'beginner' | 'intermediate' | 'advanced'
  years_experience    integer,
  onboarding_complete boolean default false,
  created_at          timestamp default now()
);


-- =============================================================================
-- Score library
-- =============================================================================

-- One uploaded PDF.
--
-- `id` has NO default: the browser mints the UUID before uploading so the
-- storage path and the row agree. `title` is the upload filename and stays that
-- way — /sheet_music/retry re-downloads by it. The display name lives in
-- work_title/composer, normalised at processing time by app/service/identify.py
-- because Audiveris' OCR of a scanned title block is unreliable.
create table pieces (
  id               uuid primary key,
  user_id          uuid references profiles (id) on delete cascade,
  title            text,                                   -- upload filename
  work_title       text,                                   -- "Prelude in C-sharp minor, Op. 3 No. 2"
  composer         text,                                   -- "Sergei Rachmaninoff (arr. Godowsky)"
  file_path        text,                                   -- storage: {user_id}/{uuid}.pdf
  musicxml_path    text,                                   -- storage: {user_id}/{uuid}.mxl
  status           text not null default 'processing'
                     check (status in ('processing', 'ready', 'failed')),
  failure_reason   text,                                   -- shown on the profile card
  processing_stage text,                                   -- 'converting' | 'analyzing' | …
  measure_offset   integer default 1,                      -- score's first measure number (0 for a pickup)
  -- One entry per cropped staff system:
  --   {page, path, bytes, cropped, start_measure, end_measure}
  page_images      jsonb default '[]'::jsonb,
  -- 'full' when the planning graph completed, 'fallback' when it failed and a
  -- deterministic equal-measure plan was written instead. The UI says so and
  -- offers a retry rather than silently shipping the downgrade.
  plan_quality     text default 'full',
  created_at       timestamp default now()
);

-- A practice-sized, musically coherent chunk, chosen by the segmenter agent.
--
-- INVARIANT: sections belong to the PIECE, never to a plan version. Every
-- ladder key and mastery row hangs off section_id, so regenerating sections
-- with fresh UUIDs would orphan all practice history. /sheet_music/retry
-- refuses once a piece has any step_attempts, for exactly this reason.
create table sections (
  id            uuid primary key default gen_random_uuid(),
  piece_id      uuid not null references pieces (id) on delete cascade,
  title         text,
  start_measure integer not null,
  end_measure   integer not null,
  difficulty    integer not null check (difficulty between 0 and 100),
  notes         text,
  -- Output of the analyze_section agent, and the input the practice ladder is
  -- derived from:
  --   {difficulty, key_challenges[], techniques[], musical_character,
  --    risk_measures[], tempo_floor, tempo_target}
  analysis_data jsonb,
  created_at    timestamp default now()
);


-- =============================================================================
-- The authored plan
-- =============================================================================

-- Versioned container. Plan revisions rewrite plan_steps only; see the
-- invariant on `sections` above.
create table practice_plans (
  id         uuid primary key default gen_random_uuid(),
  piece_id   uuid not null references pieces (id) on delete cascade,
  version    integer not null default 1,
  created_at timestamp default now()
);

-- One authored drill, from the design_drills agent.
--
-- focus_start/end_measure are NARROWER than the section: a loop on one hard
-- leap must not claim the whole passage.
create table plan_steps (
  id                  uuid primary key default gen_random_uuid(),
  plan_id             uuid not null references practice_plans (id) on delete cascade,
  section_id          uuid references sections (id) on delete cascade,
  order_index         integer not null,
  title               text not null,
  description         text not null,
  target_tempo        integer,
  drill_type          drill_type_enum not null,
  is_checkpoint       boolean default false,
  unlock_requirement  integer default 0 check (unlock_requirement between 0 and 100),
  focus_start_measure integer,
  focus_end_measure   integer,
  success_criterion   text default '',   -- objectively checkable, contains a number
  -- 'plan'         authored by the graph; shown on the piece page
  -- 'remediation'  injected by the coach when a rung isn't working
  -- 'integration'  a seam drill joining two finished sections
  source              text default 'plan',
  -- Set on remediation rows only. Ladder steps are DERIVED at request time and
  -- never stored (see app/coach/ladder.py), so these two fields exist purely so
  -- a coach-injected drill can carry the same shape as one.
  stage               text,
  metronome           text,              -- 'off' | 'optional' | 'required'
  created_at          timestamp default now()
);


-- =============================================================================
-- The practice runtime
-- =============================================================================

-- One sitting. Closed by navigator.sendBeacon on page unload.
create table practice_sessions (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references profiles (id) on delete cascade,
  piece_id      uuid not null references pieces (id) on delete cascade,
  started_at    timestamp default now(),
  ended_at      timestamp,
  total_seconds integer default 0,
  notes         text                                       -- unused by the current code
);

-- One rung attempted, with how it went.
--
-- `step_key` is NOT a foreign key, deliberately. Ladder rungs are computed from
-- the section on every request and never stored, so there is no row to point
-- at; the key is the stable derived id "{section_id}:{stage}:{start}-{end}"
-- (tempo rungs add "@{bpm}"). For a coach-injected drill it is instead the
-- plan_steps UUID. Determinism of that key is what stops progress orphaning,
-- and is covered by a test in tests/test_ladder.py.
create table step_attempts (
  id            uuid primary key,
  session_id    uuid not null references practice_sessions (id) on delete cascade,
  user_id       uuid not null references auth.users (id) on delete cascade,
  section_id    uuid not null references sections (id) on delete cascade,
  step_key      text not null,
  stage         text not null,   -- notes|thread|rhythm|technique|transition|pair|section|tempo
  seconds       integer default 0,
  tempo_reached integer,
  metronome_on  boolean default false,
  self_report   text check (self_report in ('nailed', 'shaky', 'struggling')),
  skipped       boolean default false,   -- cleared via "I already know this"
  notes         text,
  created_at    timestamptz default now()
);

-- How well a section is known, and how fresh that is.
--
-- `mastery` is capped by how far up the ladder the student has climbed
-- (scheduler.STAGE_CEILING: notes 25 · thread 40 · rhythm 55 · pair 70 ·
-- section 85 · tempo 100), so a passage only ever played in two-bar chunks
-- cannot report as mastered. It decays with
--     effective = mastery * exp(-days / (BASE_HALF_LIFE * (1 + streak)))
-- which is what makes old sections resurface for review on their own.
create table section_mastery (
  user_id           uuid not null references auth.users (id) on delete cascade,
  section_id        uuid not null references sections (id) on delete cascade,
  mastery           integer default 0,
  streak            integer default 0,        -- consecutive 'nailed' reports
  times_reviewed    integer default 0,
  reached_stage     text default 'notes',     -- furthest fully-completed stage
  last_practiced_at timestamptz default now(),
  primary key (user_id, section_id)
);


-- =============================================================================
-- Legacy — present in the database, referenced by no code
-- =============================================================================
--
-- Both predate the practice ladder and were superseded by step_attempts and
-- section_mastery. Empty, and safe to drop; kept here so the file matches what
-- the database actually contains.

create table session_activities (
  id               uuid primary key default gen_random_uuid(),
  session_id       uuid not null references practice_sessions (id) on delete cascade,
  plan_step_id     uuid references plan_steps (id) on delete cascade,
  duration_seconds integer default 0,
  tempo_used       integer,
  mistake_count    integer default 0,
  self_rating      integer check (self_rating between 1 and 5),
  completed        boolean default false,
  notes            text,
  created_at       timestamptz default now()
);

create table step_progress (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references profiles (id) on delete cascade,
  plan_step_id      uuid not null references plan_steps (id) on delete cascade,
  mastery_score     integer default 0 check (mastery_score between 0 and 100),
  confidence_score  integer default 0 check (confidence_score between 0 and 100),
  repetitions       integer default 0,
  last_attempted_at timestamp,
  completed         boolean default false,
  created_at        timestamp default now(),
  unique (user_id, plan_step_id)
);


-- =============================================================================
-- Indexes
-- =============================================================================

create index idx_sections_piece_id            on sections (piece_id);
create index idx_plan_steps_plan_id           on plan_steps (plan_id);
create index practice_sessions_piece_idx      on practice_sessions (user_id, piece_id);
create index step_attempts_key_idx            on step_attempts (user_id, step_key);
create index step_attempts_section_idx        on step_attempts (section_id);
create index idx_session_activities_session_id on session_activities (session_id);
create index idx_step_progress_user_id        on step_progress (user_id);
create index idx_step_progress_plan_step_id   on step_progress (plan_step_id);


-- =============================================================================
-- Row level security
-- =============================================================================
--
-- Enabled on every table. The backend uses the service-role key and bypasses
-- all of this; these policies exist to scope what the browser can read.

alter table profiles           enable row level security;
alter table pieces             enable row level security;
alter table sections           enable row level security;
alter table practice_plans     enable row level security;
alter table plan_steps         enable row level security;
alter table practice_sessions  enable row level security;
alter table step_attempts      enable row level security;
alter table section_mastery    enable row level security;
alter table session_activities enable row level security;
alter table step_progress      enable row level security;

-- Own row.
create policy "Users can view own profile"   on profiles for select using (auth.uid() = id);
create policy "Users can update own profile" on profiles for update using (auth.uid() = id);

create policy "Users can view own pieces"   on pieces for select using (auth.uid() = user_id);
create policy "Users can insert own pieces" on pieces for insert with check (auth.uid() = user_id);
create policy "Users can update own pieces" on pieces for update using (auth.uid() = user_id);
create policy "Users can delete own pieces" on pieces for delete using (auth.uid() = user_id);

-- Reached through the owning piece.
create policy "Users can view sections" on sections for select
  using (exists (select 1 from pieces p where p.id = sections.piece_id and p.user_id = auth.uid()));
create policy "Users can insert sections" on sections for insert
  with check (exists (select 1 from pieces p where p.id = sections.piece_id and p.user_id = auth.uid()));
create policy "Users can update sections" on sections for update
  using (exists (select 1 from pieces p where p.id = sections.piece_id and p.user_id = auth.uid()));

create policy "Users can view practice plans" on practice_plans for select
  using (exists (select 1 from pieces p where p.id = practice_plans.piece_id and p.user_id = auth.uid()));
create policy "Users can insert practice plans" on practice_plans for insert
  with check (exists (select 1 from pieces p where p.id = practice_plans.piece_id and p.user_id = auth.uid()));
create policy "Users can update practice plans" on practice_plans for update
  using (exists (select 1 from pieces p where p.id = practice_plans.piece_id and p.user_id = auth.uid()));

create policy "Users can view plan steps" on plan_steps for select
  using (exists (select 1 from practice_plans pp join pieces p on p.id = pp.piece_id
                 where pp.id = plan_steps.plan_id and p.user_id = auth.uid()));
create policy "Users can insert plan steps" on plan_steps for insert
  with check (exists (select 1 from practice_plans pp join pieces p on p.id = pp.piece_id
                      where pp.id = plan_steps.plan_id and p.user_id = auth.uid()));
create policy "Users can update plan steps" on plan_steps for update
  using (exists (select 1 from practice_plans pp join pieces p on p.id = pp.piece_id
                 where pp.id = plan_steps.plan_id and p.user_id = auth.uid()));

-- Runtime tables: read-only from the browser; the backend does every write.
create policy "own practice sessions" on practice_sessions for select using (auth.uid() = user_id);
create policy "own step attempts"     on step_attempts     for select using (auth.uid() = user_id);
create policy "own section mastery"   on section_mastery   for select using (auth.uid() = user_id);


-- =============================================================================
-- Storage
-- =============================================================================
--
-- Single private bucket `pieces`, holding three kinds of object, all under a
-- {user_id}/ prefix so the folder-name policies below scope them:
--
--   {user_id}/{piece_id}.pdf      the original upload
--   {user_id}/{piece_id}.mxl      Audiveris output (a zip container)
--   {user_id}/{piece_id}-sN.png   cropped staff systems

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'pieces', 'pieces', false, 26214400,   -- 25 MB, matching MAX_UPLOAD_BYTES
  array[
    'application/pdf',
    'application/zip',                   -- .mxl is a zip container
    'application/octet-stream',
    'application/xml',
    'text/xml',
    'application/vnd.recordare.musicxml',
    'application/vnd.recordare.musicxml+xml',
    'image/png',                         -- system crops
    'image/jpeg'
  ]
);

create policy "Users can upload their sheet music" on storage.objects for insert
  with check (bucket_id = 'pieces' and (auth.uid())::text = (storage.foldername(name))[1]);
create policy "Users can read their own files" on storage.objects for select
  using (bucket_id = 'pieces' and (auth.uid())::text = (storage.foldername(name))[1]);
create policy "Users can delete their own files" on storage.objects for delete
  using ((auth.uid())::text = (storage.foldername(name))[1]);


-- =============================================================================
-- Known inconsistencies
-- =============================================================================
--
-- Recorded rather than silently fixed, since correcting them means a migration.
--
-- 1. Mixed timestamp types. Tables from the original schema use `timestamp`
--    (no time zone); the runtime tables added later use `timestamptz`. The
--    mastery decay maths reads last_practiced_at, which is timestamptz, so the
--    calculation is unaffected.
-- 2. practice_sessions carries two identical SELECT policies ("Users can view
--    practice sessions" and "own practice sessions") because migration 007
--    added one to a table that already existed. Harmless; one can be dropped.
-- 3. practice_sessions.notes, session_activities and step_progress are unused.
