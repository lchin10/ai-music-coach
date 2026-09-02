"""The practice ladder for one section.

This is how a piece is actually taught: break it into a bar or two, learn the
notes, thread them into a line, only THEN bring in the metronome where the
rhythm is awkward, isolate the technical trouble, pair the chunks up 2 -> 4 ->
8 minding every seam, play the section through slowly, and finally build tempo.

The shape is identical for every section, which is exactly why it is plain
Python and not a model call: teaching is not something you want improvised per
piece. Everything it needs already exists on the section row —

    analysis_data.risk_measures   which bars break first
    analysis_data.techniques      rhythmic trouble vs technical trouble
    analysis_data.tempo_floor     slow-practice BPM
    analysis_data.tempo_target    performance BPM

so no piece needs reprocessing and no prompt changes.

Steps are DERIVED, never stored. Each carries a stable key
`{section_id}:{stage}:{start}-{end}`, and attempts are recorded against that
key. Nothing to insert, nothing to renumber, and no drift between the plan and
what the student is practising.
"""

CHUNK_BARS = 2
SHORT_SECTION = 6  # below this, chunk one bar at a time
TEMPO_RUNGS = (0.6, 0.8, 1.0)
DEFAULT_FLOOR = 50
DEFAULT_TARGET = 88

# Stage order is the ladder. `next_action` walks it, and mastery is capped by
# how far up it the student has got (see scheduler.STAGE_CEILING).
STAGES = ["notes", "thread", "rhythm", "technique", "transition", "pair", "section", "tempo"]

# The metronome is LOCKED until the notes are learned. You cannot click to
# notes you do not have yet, and a student left to their own devices will
# reach for it far too early.
METRONOME_OFF = "off"
METRONOME_OPTIONAL = "optional"
METRONOME_REQUIRED = "required"

# Both sets are drawn from prompts.TECHNIQUES, which the analyst is enum-bound
# to, so anything it can emit lands in one bucket or neither.
RHYTHMIC = {
    "polyrhythm",
    "trills & ornaments",
    "contrapuntal independence",
    "repeated notes",
}
TECHNICAL = {
    "wide leaps",
    "rapid passagework",
    "octaves",
    "hand crossing",
    "double thirds/sixths",
    "rapid position shifts",
    "arpeggios",
    "scales",
    "broken chords",
    "chromaticism",
}

# An authored drill's type tells us which rung its prose belongs to, so the
# ladder inherits the agent's section-specific coaching for free.
DRILL_STAGE = {
    "hands_separate": "notes",
    "slow_practice": "thread",
    "hands_together": "thread",
    "rhythm_variation": "rhythm",
    "metronome": "rhythm",
    "loop": "technique",
    "articulation_focus": "technique",
    "tempo_building": "tempo",
    "checkpoint": "section",
}


def _chunks(start: int, end: int, risky: set) -> list:
    """Tile [start, end] into practice-sized chunks.

    Two bars normally, one for a short section, and one for any chunk holding
    two or more risk measures — a chunk with two dangerous bars in it is not a
    chunk, it's a pile.
    """
    size = 1 if end - start + 1 < SHORT_SECTION else CHUNK_BARS

    out = []
    m = start
    while m <= end:
        last = min(m + size - 1, end)
        # A lone leftover bar at the end is not worth a rung of its own.
        if last == end and last == m and out:
            out[-1] = (out[-1][0], last)
        else:
            out.append((m, last))
        m = last + 1

    split = []
    for a, b in out:
        if b > a and sum(1 for r in risky if a <= r <= b) >= 2:
            split += [(i, i) for i in range(a, b + 1)]
        else:
            split.append((a, b))
    return split


def _merge_levels(chunks: list) -> list:
    """Binary merge tree over the chunks: 2 bars -> 4 -> 8 -> the section.

    Returns one list per level of `(start, end, seam)`, where `seam` is the
    last bar of the left half — the join the student is actually drilling.
    An odd chunk out is carried up unchanged and emits nothing, because it has
    already been played at its own size.
    """
    levels = []
    current = list(chunks)

    while len(current) > 1:
        merged, emitted = [], []
        for i in range(0, len(current), 2):
            if i + 1 < len(current):
                pair = (current[i][0], current[i + 1][1], current[i][1])
                merged.append((pair[0], pair[1]))
                emitted.append(pair)
            else:
                merged.append(current[i])
        levels.append(emitted)
        current = merged

    return levels


def _coach_note(authored: list, stage: str, a: int, b: int) -> str:
    """Borrow the agent's prose for this rung, when it wrote any that fits.

    Picks the authored step of the matching stage whose focus range overlaps
    ours the most. Returns "" when nothing matches — the templated text stands
    on its own.
    """
    best, best_overlap = "", 0
    for step in authored:
        if DRILL_STAGE.get(step.get("drill_type")) != stage:
            continue
        fs = step.get("focus_start_measure")
        fe = step.get("focus_end_measure")
        if fs is None or fe is None:
            continue
        overlap = min(b, fe) - max(a, fs) + 1
        if overlap > best_overlap:
            best, best_overlap = step.get("description") or "", overlap
    return best


def _step(section_id, stage, a, b, metronome, tempo, title, instructions, suffix=""):
    """`instructions` is a list of (lead, detail) pairs.

    A drill read as one paragraph is a paragraph you skim. Split into a short
    bolded instruction plus the reasoning underneath, it's something you can
    glance at mid-passage and act on.
    """
    points = [
        {"lead": lead, "detail": (detail or "").strip()}
        for lead, detail in instructions
        if lead
    ]
    return {
        "key": f"{section_id}:{stage}:{a}-{b}{suffix}",
        "section_id": section_id,
        "stage": stage,
        "focus_start_measure": a,
        "focus_end_measure": b,
        "metronome": metronome,
        "target_tempo": tempo,
        "title": title,
        "instructions": points,
        # Flat fallback, for anything that just wants text.
        "description": " ".join(f"{p['lead']}. {p['detail']}" for p in points),
        "source": "ladder",
    }


def _plan_note(authored, stage, a, b):
    """The agent's prose for this rung, as a final instruction point."""
    note = _coach_note(authored, stage, a, b)
    return [("From your plan", note)] if note else []


def _bars(a: int, b: int) -> str:
    return f"m. {a}" if a == b else f"mm. {a}–{b}"


def build(section: dict, authored_steps: list = None, level: str = "intermediate") -> list:
    """The full ladder for one section, in the order it should be practised."""
    authored = authored_steps or []
    analysis = section.get("analysis_data") or {}

    sid = section["id"]
    start = section["start_measure"]
    end = section["end_measure"]

    risky = {m for m in (analysis.get("risk_measures") or []) if start <= m <= end}
    techniques = set(analysis.get("techniques") or [])
    floor = analysis.get("tempo_floor") or DEFAULT_FLOOR
    target = analysis.get("tempo_target") or DEFAULT_TARGET
    # A target below the floor is nonsense and would invert the tempo ladder.
    target = max(target, floor)

    rhythmic = bool(techniques & RHYTHMIC)
    technical = bool(techniques & TECHNICAL) or not rhythmic

    chunks = _chunks(start, end, risky)
    steps = []

    # 1. Notes — one chunk at a time, no metronome.
    for a, b in chunks:
        hands = (
            ("Read it through", f"Take {_bars(a, b)} straight off the page.")
            if level == "advanced"
            else ("Hands separate first",
                  f"Right hand alone through {_bars(a, b)}, then left hand alone.")
        )
        steps.append(_step(
            sid, "notes", a, b, METRONOME_OFF, None,
            f"Learn the notes — {_bars(a, b)}",
            [
                hands,
                ("Settle the fingering now",
                 "Whatever you choose here is what your hands will remember, "
                 "so choose it deliberately rather than landing on it twice."),
                ("No metronome yet",
                 "You can't click to notes you don't have."),
            ] + _plan_note(authored, "notes", a, b),
        ))

    # 2. Thread — join the notes into a line, still free tempo.
    for a, b in chunks:
        steps.append(_step(
            sid, "thread", a, b, METRONOME_OFF, None,
            f"Thread it together — {_bars(a, b)}",
            [
                (f"Hands together, {_bars(a, b)}",
                 "As slow as you need. The only goal is that the line doesn't stop."),
                ("Still no metronome",
                 "You're connecting the notes, not timing them — timing is the "
                 "next rung."),
            ] + _plan_note(authored, "thread", a, b),
        ))

    # 3. Rhythm — the FIRST metronome use, and only where the writing is
    #    rhythmically awkward.
    if rhythmic:
        for a, b in chunks:
            if not any(a <= r <= b for r in risky):
                continue
            steps.append(_step(
                sid, "rhythm", a, b, METRONOME_REQUIRED, floor,
                f"Rhythm — {_bars(a, b)}",
                [
                    (f"Metronome on at {floor} bpm",
                     "Slow enough that both hands land exactly where they "
                     "should, not almost."),
                    ("Count the subdivision out loud",
                     "When the hands drift apart, counting is what puts them "
                     "back together."),
                ] + _plan_note(authored, "rhythm", a, b),
            ))

    # 4. Technique — leaps, fast passagework, position shifts. Isolated.
    if technical:
        for a, b in chunks:
            if not any(a <= r <= b for r in risky):
                continue
            steps.append(_step(
                sid, "technique", a, b, METRONOME_OPTIONAL, floor,
                f"Isolate the hard part — {_bars(a, b)}",
                [
                    (f"Take {_bars(a, b)} on its own",
                     "This is one of the bars flagged as breaking down first "
                     "under tempo, so it earns its own drill."),
                    ("Repeat the motion, not the passage",
                     "Drill the physical movement until it stops feeling like "
                     "a reach. Speed follows comfort, never the other way round."),
                ] + _plan_note(authored, "technique", a, b),
            ))

    # 5. Pair the chunks up, minding every seam. A transition can be two beats
    #    — a 4->1 across a barline — and deserves its own rung when it's near
    #    trouble, or when it's the join between the section's two halves.
    seen = {s["key"] for s in steps}
    for level_index, merges in enumerate(_merge_levels(chunks)):
        for a, b, seam in merges:
            whole = a == start and b == end
            flagged = any(seam - 1 <= r <= seam + 1 for r in risky)

            if flagged or whole:
                ta, tb = max(start, seam), min(end, seam + 1)
                landing = min(end, seam + 1)
                step = _step(
                    sid, "transition", ta, tb, METRONOME_OPTIONAL, floor,
                    f"The join into m. {landing}",
                    [
                        (f"Just the crossing into m. {landing}",
                         f"The last beat of m. {seam} into the downbeat of "
                         f"m. {landing}. Nothing before it, nothing after."),
                        ("Two beats is a real drill",
                         "Stop the moment you've landed, then start again. "
                         "Most breakdowns happen at a join, not in a bar."),
                    ],
                )
                if step["key"] not in seen:
                    seen.add(step["key"])
                    steps.append(step)

            # The top merge IS the whole section; `section` covers it.
            if whole:
                continue

            step = _step(
                sid, "pair", a, b, METRONOME_OPTIONAL, floor,
                f"Join them up — {_bars(a, b)}",
                [
                    (f"Play {_bars(a, b)} as one",
                     "You've done both halves separately. This is the first "
                     "time they have to hold together."),
                    (f"Watch the seam at m. {seam}",
                     "That's where it comes apart. If it does, go back to the "
                     "join alone rather than replaying the whole thing."),
                ] + _plan_note(authored, "pair", a, b),
                suffix=f"@{level_index}",
            )
            if step["key"] not in seen:
                seen.add(step["key"])
                steps.append(step)

    # 6. The whole section, slow. Notes and hand positions first.
    steps.append(_step(
        sid, "section", start, end, METRONOME_OPTIONAL, floor,
        f"The whole section — {_bars(start, end)}",
        [
            (f"Straight through, {_bars(start, end)}",
             "Slowly, and without stopping to fix things. Note where it "
             "wobbles and come back to those bars afterwards."),
            ("Metronome optional",
             "The point here is that the notes and hand positions hold up end "
             "to end, not that they're in time yet."),
        ] + _plan_note(authored, "section", start, end),
    ))

    # 7. Tempo, in rungs, stopping at target. Going faster is the student's
    #    choice, never the app's suggestion.
    for fraction in TEMPO_RUNGS:
        bpm = max(floor, round(target * fraction))
        steps.append(_step(
            sid, "tempo", start, end, METRONOME_REQUIRED, bpm,
            f"Build tempo — {bpm} bpm",
            [
                (f"Metronome at {bpm} bpm",
                 "Stay on this rung until it's clean three times running "
                 "before you move up."),
                ("Don't outrun yourself",
                 "Playing faster than you can control just rehearses the "
                 "mistakes at speed."),
            ] + _plan_note(authored, "tempo", start, end),
            suffix=f"@{bpm}",
        ))

    return steps


def stage_progress(steps: list, nailed_keys: set) -> list:
    """Per-stage completion for the session UI's rail.

    A 16-bar section is ~30 rungs; the student should see 8 stages, not 30
    rows. Returns one dict per stage the ladder actually emitted.
    """
    out = []
    for stage in STAGES:
        keys = [s["key"] for s in steps if s["stage"] == stage]
        if not keys:
            continue
        done = sum(1 for k in keys if k in nailed_keys)
        out.append({"stage": stage, "total": len(keys), "done": done,
                    "complete": done == len(keys)})
    return out
