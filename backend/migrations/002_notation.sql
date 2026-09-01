-- Phase 3: notation rendering.
-- Run in the Supabase SQL editor after 001.

alter table pieces
  -- Path in the `pieces` storage bucket to the Audiveris MusicXML. Previously
  -- parsed and thrown away with the temp dir; OSMD renders straight from it.
  add column if not exists musicxml_path text,
  -- The score's first measure number (0 when it opens with a pickup).
  -- sections.start_measure uses the score's own numbering, while OSMD counts
  -- rendered measures from 1 — this is what maps between them. See
  -- frontend/src/lib/measures.ts, the only place the conversion happens.
  add column if not exists measure_offset int default 1;
