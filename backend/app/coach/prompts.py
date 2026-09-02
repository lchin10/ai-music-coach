"""Prompt and tool schema for the remediation agent.

Kept out of app/graph/prompts.py so the planning pipeline's prompts are not
touched at all — this only borrows its enums.
"""

from app.graph.prompts import DRILL_TYPES

REMEDIATE_SYSTEM = """You are an expert piano teacher sitting next to a student who has just told you a drill isn't working.

They are partway up a practice ladder for one section:
notes (learn the notes, no metronome) -> thread (join them, no metronome) -> rhythm (metronome enters) -> technique (isolate leaps and fast passagework) -> transition (drill a seam) -> pair (2 bars -> 4 -> 8) -> section (whole thing, slow) -> tempo (metronome ladder to target).

They already tried the obvious fix — a narrower range and a slower tempo — and it still isn't landing. So do NOT just repeat that. Diagnose WHY this specific passage is failing for this student and prescribe a different angle: a different hand, a rhythm variation, a blocked-chord reduction, a fingering rethink, a physical motion to isolate.

Rules:
- 1-3 drills, in the order they should be done.
- Every focus range must lie INSIDE the failing step's section.
- No drill may be faster than the step that just failed.
- If the student is at the notes or thread stage, do NOT prescribe a metronome — they don't have the notes yet.
- Reference the actual musical content from the analysis. "Block the LH into chords for mm. 23-24 so the hand learns the shape before the arpeggio" is useful; "practise slowly" is not."""

REMEDIATE_TOOL = {
    "name": "prescribe_drills",
    "description": "Prescribe 1-3 narrower drills for a step the student is stuck on.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["diagnosis", "drills"],
        "properties": {
            "diagnosis": {
                "type": "string",
                "description": "One sentence on why this passage is failing for this student.",
            },
            "drills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "title",
                        "description",
                        "drill_type",
                        "target_tempo",
                        "focus_start_measure",
                        "focus_end_measure",
                        "use_metronome",
                    ],
                    "properties": {
                        "title": {"type": "string"},
                        "description": {
                            "type": "string",
                            "description": "Specific instruction referencing real musical content.",
                        },
                        "drill_type": {"type": "string", "enum": DRILL_TYPES},
                        "target_tempo": {
                            "type": "integer",
                            "description": "BPM. Never above the failing step's tempo.",
                        },
                        "focus_start_measure": {"type": "integer"},
                        "focus_end_measure": {"type": "integer"},
                        "use_metronome": {"type": "boolean"},
                    },
                },
            },
        },
    },
}
