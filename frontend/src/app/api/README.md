## Database

### auth.users

    id
    email
    password
    name

### profiles
    id UUID (PK, references auth.users.id)
    name TEXT
    piano_level TEXT
    years_experience INT
    created_at TIMESTAMP

### pieces

    id (uuid, pk)
    user_id (uuid, fk → profiles)
    title
    file_path
    musicxml_path
    status ("processing", "ready", "failed")
    failure_reason
    created_at

### sections

    id (uuid, pk)
    piece_id (fk)
    title
    start_measure
    end_measure
    difficulty (0-100)
    notes (text)
    analysis_data (jsonb)
    created_at

### practice_plans

    id (uuid, pk)
    piece_id (fk)
    version (int)
    created_at

### plan_steps

    id (uuid, pk)
    plan_id (fk)
    section_id (fk, nullable)
    order_index (int)
    title
    description
    target_tempo (int)
    drill_type ("hands_separate", "hands_together", "loop", "slow_practice", "tempo_building", "rhythm_variation", "metronome", "articulation_focus", "checkpoint")
    is_checkpoint
    unlock_requirement (0-100)
    created_at

### practice_sessions

    id (uuid, pk)
    user_id (fk)
    piece_id (fk)
    started_at
    ended_at
    notes

### session_activities

    id (uuid, pk)
    session_id (fk)
    plan_step_id (fk)
    duration_seconds
    tempo_used
    mistake_count
    self_rating (1-5)
    completed
    notes
    created_at

### step_progress

    id (uuid, pk)
    user_id (fk)
    plan_step_id (fk)
    mastery_level (0–100)
    confidence_score (0-100)
    repititions
    last_attempted_at
    completed
    created_at

