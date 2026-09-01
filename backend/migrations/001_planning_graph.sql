-- Phase 1: multi-agent planning graph.
-- Run in the Supabase SQL editor before deploying the new backend — the
-- processor writes these columns and the inserts fail without them.

-- Per-node progress for the upload-confirmation page.
alter table pieces
  add column if not exists processing_stage text;

-- Steps drill a NARROWER range than their section (a loop on one hard leap
-- must not claim the whole section). Nothing reads these until Phase 3, but
-- adding them now avoids backfilling every existing plan later.
alter table plan_steps
  add column if not exists focus_start_measure int,
  add column if not exists focus_end_measure   int,
  -- Objectively checkable, contains a number: "3 clean run-throughs at 72 bpm".
  -- Phase 3's scheduler gates advancement on this instead of on vibes.
  add column if not exists success_criterion   text default '',
  -- 'plan' | 'remediation' | 'integration' | 'review' — lets the Phase 3 coach
  -- inject ad-hoc drills into the same table without polluting the authored plan.
  add column if not exists source               text default 'plan';

-- INVARIANT (Decision A): sections belong to the PIECE, not the plan version.
-- Plan revisions rewrite plan_steps only. Regenerating sections with fresh
-- UUIDs would silently orphan every Phase 3 mastery and progress row.
