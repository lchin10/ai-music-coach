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
    file_url
    created_at
    status ("processing", "ready", "failed")

### sections

    id (uuid, pk)
    piece_id (fk)
    start_measure
    end_measure
    difficulty (int or enum)
    notes (text)

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
    tempo
    drill_type (e.g. "hands_separate", "loop", etc.)

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
    section_id (fk)
    duration_seconds
    tempo_used
    notes

### section_progress

    id (uuid, pk)
    user_id (fk)
    section_id (fk)
    mastery_level (0–100)
    last_practiced_at

