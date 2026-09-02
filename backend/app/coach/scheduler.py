"""What to practise next, and how well it's known.

Pure functions over plain dicts — no Supabase client, no model, no mocks in
the tests. Tapping "next" has to answer instantly, and every rule here is
arithmetic.

The two ideas that make it behave like a teacher rather than a checklist:

  * mastery is CAPPED by how far up the ladder you've climbed, so you cannot
    read 90% on a passage you've only ever played in two-bar chunks; and
  * mastery DECAYS, so sections you learned a fortnight ago resurface on their
    own. Review debt and revisiting fall out of the arithmetic — no agent.
"""

import math
from datetime import datetime, timezone

from app.coach import ladder

REPORT_WEIGHT = {"nailed": 1.0, "shaky": 0.6, "struggling": 0.25}

ALPHA = 0.4                # how fast one attempt moves the running mastery
BASE_HALF_LIFE = 4.0       # days, at streak 0
LEARNED = 70               # "this section is known"
REVIEW_FLOOR = 55          # decayed below this and it owes a review
UNLOCK_STAGE = "pair"      # the next section opens once this one is paired up
SEAM_BARS = 2              # bars either side of a section join

# You have not mastered a passage you have only played two bars at a time.
STAGE_CEILING = {
    "notes": 25,
    "thread": 40,
    "rhythm": 55,
    "technique": 55,
    "transition": 55,
    "pair": 70,
    "section": 85,
    "tempo": 100,
}


def _parse(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return datetime.now(timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Mastery
# --------------------------------------------------------------------------


def score_attempt(self_report: str, tempo_reached=None, target_tempo=None) -> float:
    """One attempt, scored 0-100.

    Tempo only counts when the step actually had one — a `notes` chunk is
    deliberately untimed, so scoring it against a BPM would punish the student
    for following the ladder.
    """
    weight = REPORT_WEIGHT.get(self_report, 0.5)
    if target_tempo and tempo_reached:
        factor = 0.5 + 0.5 * min(1.0, tempo_reached / target_tempo)
    else:
        factor = 1.0
    return round(100 * weight * factor, 1)


def completed_stage(steps: list, nailed: set):
    """The furthest ladder stage whose every step has been nailed."""
    last = None
    for stage in ladder.STAGES:
        keys = [s["key"] for s in steps if s["stage"] == stage]
        if not keys:
            continue
        if all(k in nailed for k in keys):
            last = stage
        else:
            break
    return last


def ceiling_for(steps: list, nailed: set) -> int:
    done = completed_stage(steps, nailed)
    return STAGE_CEILING[done] if done else STAGE_CEILING[ladder.STAGES[0]]


def update_mastery(prev: float, streak: int, sample: float, ceiling: int = 100):
    """Exponential moving average, clamped to what the ladder allows."""
    value = prev + ALPHA * (sample - prev)
    return int(round(min(value, ceiling))), streak


def bump_streak(streak: int, self_report: str) -> int:
    return streak + 1 if self_report == "nailed" else 0


def decayed(mastery: float, streak: int, last_practiced_at, now=None) -> float:
    """What the section is worth today.

    Half-life grows with the streak: drilled once it fades in days, nailed
    five sessions running it holds for weeks.
    """
    now = now or datetime.now(timezone.utc)
    days = max(0.0, (now - _parse(last_practiced_at)).total_seconds() / 86400)
    half_life = BASE_HALF_LIFE * (1 + max(0, streak))
    return mastery * math.exp(-days / half_life)


# --------------------------------------------------------------------------
# What next
# --------------------------------------------------------------------------


def _action(kind, section, step, why):
    return {"kind": kind, "section_id": section["id"],
            "section_title": section.get("title"), "step": step, "why": why}


def _integration_step(a: dict, b: dict) -> dict:
    """A seam drill joining two finished sections.

    Deterministic, like everything else on the ladder — the join between two
    sections is the same exercise every time.
    """
    start = max(a["start_measure"], a["end_measure"] - SEAM_BARS + 1)
    end = min(b["end_measure"], b["start_measure"] + SEAM_BARS - 1)
    floor = min(
        (s.get("analysis_data") or {}).get("tempo_floor") or ladder.DEFAULT_FLOOR
        for s in (a, b)
    )
    return {
        "key": f"{a['id']}+{b['id']}:integration",
        "section_id": b["id"],
        "stage": "integration",
        "focus_start_measure": start,
        "focus_end_measure": end,
        "metronome": ladder.METRONOME_OPTIONAL,
        "target_tempo": floor,
        "title": f"Join “{a.get('title')}” into “{b.get('title')}”",
        "instructions": [
            {"lead": f"Play mm. {start}–{end} as one",
             "detail": "You know both halves. This is the first time they have "
                       "to run into each other."},
            {"lead": f"The crossing at m. {a['end_measure']} into "
                     f"m. {b['start_measure']} is the whole exercise",
             "detail": "If it breaks, drill just those two bars rather than "
                       "restarting the passage."},
        ],
        "description": (
            f"You know both halves. Now play mm. {start}–{end} as one — the "
            f"crossing at m. {a['end_measure']} into m. {b['start_measure']} "
            f"is the whole exercise."
        ),
        "source": "integration",
    }


def next_action(sections, ladders, attempts, mastery, remediation=None, now=None):
    """The single next thing to practise.

    sections    ordered by start_measure
    ladders     {section_id: [ladder steps]}
    attempts    [{section_id, step_key, stage, self_report, created_at}]
    mastery     {section_id: {mastery, streak, last_practiced_at}}
    remediation [step dicts] queued by the coach, keyed by their row id
    """
    now = now or datetime.now(timezone.utc)
    nailed = {a["step_key"] for a in attempts if a.get("self_report") == "nailed"}
    by_id = {s["id"]: s for s in sections}

    if not sections:
        return {"kind": "done", "section_id": None, "step": None,
                "why": "This piece has no sections yet."}

    # 1. A queued breakdown comes before retrying the thing that failed.
    for step in remediation or []:
        if step["key"] not in nailed:
            section = by_id.get(step["section_id"]) or sections[0]
            return _action("remediation", section, step,
                           "Let's break this down before trying it again.")

    # 2. Resume where the student left off.
    recent = sorted(attempts, key=lambda a: _parse(a.get("created_at")))
    if recent:
        section = by_id.get(recent[-1]["section_id"])
        if section:
            for step in ladders.get(section["id"], []):
                if step["key"] not in nailed:
                    return _action("resume", section, step,
                                   "Picking up where you left off.")

    # 3. Review debt — something learned has faded.
    for section in sections:
        row = mastery.get(section["id"])
        if not row or row.get("mastery", 0) < LEARNED:
            continue
        if decayed(row["mastery"], row.get("streak", 0),
                   row.get("last_practiced_at"), now) >= REVIEW_FLOOR:
            continue
        # Re-enter at the section stage, not back down at note-learning.
        for step in ladders.get(section["id"], []):
            if step["stage"] == "section":
                return _action("review", section, step,
                               "You haven't touched this in a while — worth a pass.")

    # 4. Two adjacent finished sections that have never been played joined.
    for a, b in zip(sections, sections[1:]):
        a_done = completed_stage(ladders.get(a["id"], []), nailed)
        b_done = completed_stage(ladders.get(b["id"], []), nailed)
        if not a_done or not b_done:
            continue
        if ladder.STAGES.index(a_done) < ladder.STAGES.index("section"):
            continue
        if ladder.STAGES.index(b_done) < ladder.STAGES.index("section"):
            continue
        step = _integration_step(a, b)
        if step["key"] not in nailed:
            return _action("integration", b, step,
                           "Both sections are solid — time to join them.")

    # 5. Advance, once the previous section is paired up.
    unlock_index = ladder.STAGES.index(UNLOCK_STAGE)
    for i, section in enumerate(sections):
        steps = ladders.get(section["id"], [])
        pending = [s for s in steps if s["key"] not in nailed]
        if not pending:
            continue
        if i > 0:
            prev_done = completed_stage(ladders.get(sections[i - 1]["id"], []), nailed)
            if not prev_done or ladder.STAGES.index(prev_done) < unlock_index:
                # Locked. The previous section still owes work, which resume
                # or an earlier rule would have surfaced.
                continue
        return _action("advance", section, pending[0], "Next up.")

    # 6. Everything is at tempo.
    return {
        "kind": "run_through",
        "section_id": sections[0]["id"],
        "section_title": None,
        "step": None,
        "why": "Every section is at tempo — play the whole piece through.",
    }


def locked_sections(sections, ladders, nailed) -> set:
    """Which sections the UI should show with a padlock."""
    unlock_index = ladder.STAGES.index(UNLOCK_STAGE)
    locked = set()
    for i, section in enumerate(sections):
        if i == 0:
            continue
        prev_done = completed_stage(ladders.get(sections[i - 1]["id"], []), nailed)
        if not prev_done or ladder.STAGES.index(prev_done) < unlock_index:
            locked.add(section["id"])
    return locked
