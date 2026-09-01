"""Deterministic plan validation.

Produces a report, not an exception. Hard findings are real defects and force
a revision; soft findings are advisory and the critic gets the final word —
an unusually long section may be the musically correct choice.

Pure functions over plain dicts: no music21, no network, no model.
"""

from app.graph.prompts import DRILL_TYPES

MIN_TEMPO, MAX_TEMPO = 30, 240
MIN_SECTION_MEASURES = 2
MIN_STEPS, MAX_STEPS = 2, 8
MAX_TOTAL_STEPS = 250


def _hard(report, message):
    report["hard"].append(message)


def _soft(report, message):
    report["soft"].append(message)


def validate(sections: list, features: dict, profile: dict) -> dict:
    """sections: [{index, title, start_measure, end_measure, analysis, steps}]"""
    report = {"hard": [], "soft": []}
    # The score's own numbering, not a 1..N count — a pickup measure is 0.
    first_measure = features["score"].get("first_measure", 1)
    last_measure = features["score"].get("last_measure") or features["score"]["total_measures"]
    score_tempos = [t["bpm"] for t in features["score"].get("tempos", []) if t.get("bpm")]
    score_tempo = min(score_tempos) if score_tempos else None
    level = (profile.get("piano_level") or "").lower()

    ordered = sorted(sections, key=lambda s: s["start_measure"])

    # ---------------- structural (hard) ----------------
    if not ordered:
        _hard(report, "plan has no sections")
        return report

    if ordered[0]["start_measure"] != first_measure:
        _hard(
            report,
            f"plan starts at measure {ordered[0]['start_measure']}, expected {first_measure}",
        )

    if ordered[-1]["end_measure"] != last_measure:
        _hard(
            report,
            f"plan ends at measure {ordered[-1]['end_measure']}, expected {last_measure}",
        )

    for section in ordered:
        start, end = section["start_measure"], section["end_measure"]
        label = f"section '{section['title']}'"

        if start > end:
            _hard(report, f"{label} has start_measure {start} after end_measure {end}")
        if start < first_measure or end > last_measure:
            _hard(
                report,
                f"{label} range {start}-{end} falls outside {first_measure}-{last_measure}",
            )
        if end - start + 1 < MIN_SECTION_MEASURES:
            _hard(report, f"{label} is shorter than {MIN_SECTION_MEASURES} measures")

    for previous, following in zip(ordered, ordered[1:]):
        gap = following["start_measure"] - previous["end_measure"]
        if gap > 1:
            _hard(
                report,
                f"gap between measures {previous['end_measure']} and {following['start_measure']}",
            )
        elif gap < 1:
            _hard(
                report,
                f"overlap between '{previous['title']}' and '{following['title']}' "
                f"at measure {following['start_measure']}",
            )

    # ---------------- steps (hard) ----------------
    total_steps = 0
    seen_order = []

    for section in ordered:
        steps = section.get("steps", [])
        label = f"section '{section['title']}'"
        total_steps += len(steps)

        if not steps:
            _hard(report, f"{label} has no steps")
            continue

        checkpoints = [s for s in steps if s.get("is_checkpoint")]
        if not checkpoints:
            _hard(report, f"{label} has no checkpoint step")
        elif not steps[-1].get("is_checkpoint"):
            _hard(report, f"{label}'s final step is not the checkpoint")

        tempos = [s["target_tempo"] for s in steps]
        if any(b < a for a, b in zip(tempos, tempos[1:])):
            _hard(report, f"{label} has a target_tempo that decreases: {tempos}")

        for step in steps:
            if step["drill_type"] not in DRILL_TYPES:
                _hard(report, f"{label}: unknown drill_type '{step['drill_type']}'")

            if not 0 <= step.get("unlock_requirement", 0) <= 100:
                _hard(report, f"{label}: unlock_requirement outside 0-100")

            focus_start = step.get("focus_start_measure")
            focus_end = step.get("focus_end_measure")
            if focus_start is None or focus_end is None:
                _hard(report, f"{label}: step '{step['title']}' has no focus range")
            elif not (
                section["start_measure"] <= focus_start <= focus_end <= section["end_measure"]
            ):
                _hard(
                    report,
                    f"{label}: step '{step['title']}' focus {focus_start}-{focus_end} "
                    f"escapes its section {section['start_measure']}-{section['end_measure']}",
                )

            seen_order.append(step.get("order_index"))

    if total_steps > MAX_TOTAL_STEPS:
        _hard(report, f"plan has {total_steps} steps, over the {MAX_TOTAL_STEPS} cap")

    assigned = [o for o in seen_order if o is not None]
    if assigned and sorted(assigned) != list(range(len(assigned))):
        _hard(report, "order_index values are not dense and unique across the plan")

    # ---------------- musical sanity (soft) ----------------
    for section in ordered:
        label = f"section '{section['title']}'"
        steps = section.get("steps", [])

        if steps and not MIN_STEPS <= len(steps) <= MAX_STEPS:
            _soft(report, f"{label} has {len(steps)} steps, outside the usual {MIN_STEPS}-{MAX_STEPS}")

        for step in steps:
            tempo = step["target_tempo"]
            if not MIN_TEMPO <= tempo <= MAX_TEMPO:
                _soft(report, f"{label}: target_tempo {tempo} outside {MIN_TEMPO}-{MAX_TEMPO}")

            criterion = step.get("success_criterion", "")
            if not criterion:
                _soft(report, f"{label}: step '{step['title']}' has no success_criterion")
            elif not any(c.isdigit() for c in criterion):
                _soft(
                    report,
                    f"{label}: success_criterion '{criterion}' has no number — not checkable",
                )

        if score_tempo and steps:
            final = steps[-1]["target_tempo"]
            if final > score_tempo:
                _soft(
                    report,
                    f"{label}: final tempo {final} exceeds the score's {score_tempo} bpm marking",
                )

    # ---------------- personalization (soft) ----------------
    if level.startswith("begin"):
        for section in ordered:
            steps = section.get("steps", [])
            if steps and not any(s["drill_type"] == "hands_separate" for s in steps):
                _soft(
                    report,
                    f"section '{section['title']}' has no hands_separate step for a beginner",
                )
            if score_tempo and steps and steps[-1]["target_tempo"] > score_tempo * 0.9:
                _soft(
                    report,
                    f"section '{section['title']}' asks a beginner for "
                    f"{steps[-1]['target_tempo']} bpm, over 90% of score tempo",
                )

    if level.startswith("adv"):
        for section in ordered:
            steps = section.get("steps", [])
            if steps and all(s["drill_type"] == "hands_separate" for s in steps):
                _soft(
                    report,
                    f"section '{section['title']}' is entirely hands_separate for an advanced player",
                )

    return report


def summarize(report: dict) -> str:
    """Render the report for the critic's prompt."""
    if not report["hard"] and not report["soft"]:
        return "Validator: no findings."

    lines = []
    if report["hard"]:
        lines.append("HARD findings (real defects, must be fixed):")
        lines += [f"  - {m}" for m in report["hard"]]
    if report["soft"]:
        lines.append("SOFT findings (advisory — use your judgement):")
        lines += [f"  - {m}" for m in report["soft"]]
    return "\n".join(lines)
