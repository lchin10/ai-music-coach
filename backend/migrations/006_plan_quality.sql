-- Make a fallback plan admit that it is one, and drop checkpointing.
--
-- When the graph failed, the piece still went status='ready' with a generic
-- equal-measure plan and no signal, so a silent downgrade looked identical to
-- the real product. plan_quality lets the UI say so and offer a retry.

alter table pieces
  add column if not exists plan_quality text default 'full';

-- Existing rows predate the column; anything already ready was full or
-- fallback with no way to tell, so leave the default and let a retry fix it.

-- LangGraph checkpointing is removed. Resume was never wired up: thread_id is
-- the piece_id and the frontend mints a new UUID per upload, so no run ever
-- read a checkpoint. It saved nothing and destroyed two paid runs.
drop table if exists checkpoint_writes;
drop table if exists checkpoint_blobs;
drop table if exists checkpoints;
drop table if exists checkpoint_migrations;
