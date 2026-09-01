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
