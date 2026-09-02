"""When a rung isn't working.

The ladder makes the free version genuinely good: there is always a rung
below, so `narrow` doesn't have to guess — it knows what "easier" means for
each stage. That's the first "Struggling" tap: instant, no tokens.

Only a SECOND tap on the same step pays for `diagnose`, which asks why this
particular passage is failing rather than just making it smaller. If that call
fails, or returns anything that doesn't validate, we fall back to `narrow`.
An optional agent must never dead-end a session.
"""

from app.coach import ladder
from app.coach.prompts import REMEDIATE_SYSTEM, REMEDIATE_TOOL
from app.graph.prompts import DRILL_TYPES

TEMPO_DROP = 0.8
TEMPO_MIN = 40
MAX_DRILLS = 3


def _clamp(a, b, section):
    lo, hi = section["start_measure"], section["end_measure"]
    a, b = max(lo, min(a, hi)), max(lo, min(b, hi))
    return (a, b) if a <= b else (b, a)


def _slower(tempo, floor):
    return floor if not tempo else max(TEMPO_MIN, round(tempo * TEMPO_DROP))


def _drill(section, stage, a, b, tempo, metronome, title, lead, detail=""):
    """One instruction point, same shape the ladder emits (see ladder._step)."""
    a, b = _clamp(a, b, section)
    return {
        "section_id": section["id"],
        "stage": stage,
        "focus_start_measure": a,
        "focus_end_measure": b,
        "target_tempo": tempo,
        "metronome": metronome,
        "title": title,
        "instructions": [{"lead": lead, "detail": detail.strip()}],
        "description": f"{lead}. {detail}".strip(),
        "source": "remediation",
    }


def narrow(step: dict, section: dict) -> list:
    """The rung below the one that's failing. Free, instant, always available."""
    analysis = section.get("analysis_data") or {}
    floor = analysis.get("tempo_floor") or ladder.DEFAULT_FLOOR
    a = step["focus_start_measure"]
    b = step["focus_end_measure"]
    stage = step.get("stage")
    mid = a + (b - a) // 2
    slower = max(TEMPO_MIN, round((step.get("target_tempo") or floor) * TEMPO_DROP))

    if stage == "notes":
        return [_drill(
            section, "notes", a, a, None, ladder.METRONOME_OFF,
            f"One bar, one hand — m. {a}",
            f"Right hand alone through m. {a}, then left hand alone",
            "Don't put them together until each one runs without you thinking "
            "about it.",
        )]

    if stage == "thread":
        return [_drill(
            section, "notes", a, mid, None, ladder.METRONOME_OFF,
            f"Back to the notes — mm. {a}–{mid}",
            f"Hands separate again through mm. {a}–{mid}",
            "Threading isn't sticking because the notes aren't quite there "
            "yet. Rebuild the first half, then rejoin.",
        )]

    if stage == "rhythm":
        return [_drill(
            section, "rhythm", a, b, slower, ladder.METRONOME_REQUIRED,
            f"Same bars, {slower} bpm",
            f"Drop the metronome to {slower} bpm",
            "If the hands still don't line up, count the subdivision out loud "
            "while you play — that usually finds the beat you're rushing.",
        )]

    if stage in ("technique", "integration"):
        return [_drill(
            section, "technique", a, a, floor, ladder.METRONOME_OPTIONAL,
            f"Just m. {a}",
            f"One bar — m. {a}, hands together",
            "As slow as it takes. Repeat the motion until it stops feeling "
            "like a reach.",
        )]

    if stage == "pair":
        landing = min(b, mid + 1)
        return [_drill(
            section, "transition", mid, landing, floor,
            ladder.METRONOME_OPTIONAL,
            f"Only the seam — m. {mid} into m. {landing}",
            f"Play only the crossing into m. {landing}",
            "Forget the rest of the passage. The last beat of "
            f"m. {mid} into that downbeat, over and over.",
        )]

    if stage == "transition":
        # A transition is ALREADY just the seam, so narrowing the range again
        # would hand back the same drill. Go at the landing instead.
        return [_drill(
            section, "technique", b, b, slower, ladder.METRONOME_OPTIONAL,
            f"Land on m. {b}",
            f"From a dead stop, play only the downbeat of m. {b}",
            "Both hands, until the shape is automatic. Then add the beat "
            f"before it back in at {slower} bpm.",
        )]

    if stage == "section":
        return [_drill(
            section, "pair", a, mid, floor, ladder.METRONOME_OPTIONAL,
            f"Half the section — mm. {a}–{mid}",
            f"Just mm. {a}–{mid} for now",
            "The whole thing is too much to hold at once. Rebuild it from the "
            "first half, then add the second back on.",
        )]

    if stage == "tempo":
        return [_drill(
            section, "tempo", a, b, slower, ladder.METRONOME_REQUIRED,
            f"Back a rung — {slower} bpm",
            f"Come back down to {slower} bpm",
            "You've gone up too early. Sit here until it's clean three times "
            "running, then move.",
        )]

    # Unknown stage: halve the range and slow down. Never return nothing.
    return [_drill(
        section, stage or "technique", a, mid, _slower(step.get("target_tempo"), floor),
        ladder.METRONOME_OPTIONAL, f"Narrower — mm. {a}–{mid}",
        f"Half the range — mm. {a}–{mid} — and slower",
        "Smaller and slower is nearly always the way out.",
    )]


def _valid(drills, step, section) -> bool:
    if not drills or len(drills) > MAX_DRILLS:
        return False
    lo, hi = section["start_measure"], section["end_measure"]
    ceiling = step.get("target_tempo") or (section.get("analysis_data") or {}).get(
        "tempo_target") or ladder.DEFAULT_TARGET

    for d in drills:
        a, b = d.get("focus_start_measure"), d.get("focus_end_measure")
        if a is None or b is None or a > b or a < lo or b > hi:
            return False
        if d.get("drill_type") not in DRILL_TYPES:
            return False
        if (d.get("target_tempo") or 0) > ceiling:
            return False
    return True


def diagnose(step: dict, section: dict, attempts: list, profile: dict) -> list:
    """One cheap Opus call. Falls back to `narrow` on anything unexpected."""
    # Imported here so the practice endpoints don't pull in the Anthropic
    # client (or need an API key) unless someone actually gets stuck twice.
    import json

    from app.graph import nodes

    analysis = section.get("analysis_data") or {}
    history = [
        {"stage": a.get("stage"), "self_report": a.get("self_report"),
         "tempo_reached": a.get("tempo_reached")}
        for a in attempts[-6:]
    ]

    cached = (
        f"Section “{section.get('title')}” covers measures "
        f"{section['start_measure']}–{section['end_measure']}.\n\n"
        f"Analysis:\n{json.dumps(analysis, indent=1)}"
    )
    user = (
        f"Student level: {profile.get('piano_level', 'intermediate')} "
        f"({profile.get('years_experience', '?')} years).\n\n"
        f"The step that isn't working:\n{json.dumps(step, indent=1, default=str)}\n\n"
        f"Their recent attempts on it:\n{json.dumps(history, indent=1)}\n\n"
        f"They have already tried a narrower range and a slower tempo. "
        f"Diagnose it and prescribe a different angle."
    )

    try:
        result = nodes._call(
            REMEDIATE_SYSTEM, cached, user, REMEDIATE_TOOL, effort="low"
        )
        drills = result.get("drills") or []
        if not _valid(drills, step, section):
            print("[coach] remediation failed validation, narrowing instead")
            return narrow(step, section)

        diagnosis = (result.get("diagnosis") or "").strip()
        out = []
        for d in drills:
            out.append(_drill(
                section,
                step.get("stage") or "technique",
                d["focus_start_measure"],
                d["focus_end_measure"],
                d.get("target_tempo"),
                ladder.METRONOME_REQUIRED if d.get("use_metronome")
                else ladder.METRONOME_OPTIONAL,
                d["title"],
                d["title"],
                d["description"],
            ))
        if diagnosis:
            # The diagnosis leads: it's why the drills that follow are these
            # drills, and it's the part worth reading first.
            out[0]["instructions"].insert(
                0, {"lead": "What's going wrong", "detail": diagnosis}
            )
            out[0]["description"] = f"{diagnosis} {out[0]['description']}"
        return out
    except Exception as e:
        print(f"[coach] remediation call failed ({e}); narrowing instead")
        return narrow(step, section)
