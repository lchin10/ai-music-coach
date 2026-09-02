"""Expected Supabase schema, and a check for drift.

Single source of truth for the columns the backend reads and writes. Keep it in
sync when a migration adds a column — the check is only as good as this dict.
"""

EXPECTED = {
    "profiles": ["id", "piano_level", "years_experience", "onboarding_complete"],
    "pieces": [
        "id", "user_id", "title", "file_path", "status",
        "failure_reason",      # migration 000
        "processing_stage",    # migration 001
        "musicxml_path", "measure_offset",  # migration 002
        "page_images",                      # migration 005
        "plan_quality",                     # migration 006
    ],
    "sections": [
        "id", "piece_id", "title", "start_measure", "end_measure",
        "difficulty", "notes", "analysis_data",
    ],
    "practice_plans": ["id", "piece_id", "version"],
    "plan_steps": [
        "id", "plan_id", "section_id", "order_index", "title", "description",
        "target_tempo", "drill_type", "is_checkpoint", "unlock_requirement",
        # migration 001
        "focus_start_measure", "focus_end_measure", "success_criterion", "source",
        "stage", "metronome",  # migration 007, remediation drills only
    ],
    # migration 007 — the practice runtime
    "practice_sessions": [
        "id", "user_id", "piece_id", "started_at", "ended_at", "total_seconds",
    ],
    "step_attempts": [
        "id", "session_id", "user_id", "section_id", "step_key", "stage",
        "created_at", "seconds", "tempo_reached", "metronome_on",
        "self_report", "skipped", "notes",
    ],
    "section_mastery": [
        "user_id", "section_id", "mastery", "streak", "times_reviewed",
        "reached_stage", "last_practiced_at",
    ],
}


def check(supabase) -> dict:
    """Probe every expected column. Returns {table: [missing columns]}.

    One query per table when healthy; only a failing table costs one query per
    column to pin down which ones are actually absent.
    """
    missing = {}

    for table, columns in EXPECTED.items():
        try:
            supabase.table(table).select(",".join(columns)).limit(1).execute()
            continue
        except Exception as e:
            absent = []
            for column in columns:
                try:
                    supabase.table(table).select(column).limit(1).execute()
                except Exception:
                    absent.append(column)
            # The table itself is missing, not just columns.
            missing[table] = absent or [f"<table unreadable: {e}>"]

    return missing
