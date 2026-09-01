"""Deterministic music21 feature extraction.

Everything the planning agents know about the score comes from here. music21
is better and cheaper at this than an LLM, so no model is involved — the
output is a compact table that becomes the cached prefix shared by every
downstream call, which is why the rows are terse tuples rather than prose.
"""

from collections import Counter
from statistics import mean

# Anything above this is a book or an OMR blow-up, not a piece. Checked
# before the fan-out, where cost actually lives.
MAX_MEASURES = 400


class TooLongError(Exception):
    """Raised before any token is spent."""


def _pitches(measure):
    return [p for n in measure.recurse().notes for p in n.pitches]


def _max_melodic_interval(measure):
    """Largest semitone jump between consecutive note onsets — leap detection."""
    tops = [max(n.pitches).midi for n in measure.recurse().notes]
    if len(tops) < 2:
        return 0
    return max(abs(b - a) for a, b in zip(tops, tops[1:]))


def _shortest_duration(measure):
    durs = [n.duration.quarterLength for n in measure.recurse().notes if n.duration.quarterLength]
    return min(durs) if durs else 0


def _measure_row(measure, part_index):
    notes = list(measure.recurse().notes)
    chords = [n for n in notes if len(n.pitches) > 1]
    pitches = _pitches(measure)

    row = {
        "part": part_index,
        "notes": len(notes),
        "chords": len(chords),
        # Chord span in semitones reveals 9ths/10ths a small hand can't grab.
        "max_chord_span": max(
            (max(c.pitches).midi - min(c.pitches).midi for c in chords), default=0
        ),
        "low": min(pitches).midi if pitches else None,
        "high": max(pitches).midi if pitches else None,
        "max_leap": _max_melodic_interval(measure),
        "shortest": _shortest_duration(measure),
        "rests": len(list(measure.recurse().getElementsByClass("Rest"))),
        "accidentals": sum(1 for p in pitches if p.accidental is not None),
    }

    dynamics = [d.value for d in measure.recurse().getElementsByClass("Dynamic")]
    if dynamics:
        row["dynamics"] = dynamics

    articulations = sorted(
        {a.name for n in notes for a in n.articulations}
    )
    if articulations:
        row["articulations"] = articulations

    ornaments = sorted(
        {e.name for n in notes for e in n.expressions if hasattr(e, "name")}
    )
    if ornaments:
        row["ornaments"] = ornaments

    if any(n.duration.isGrace for n in notes):
        row["grace"] = True

    if any(n.duration.tuplets for n in notes):
        row["tuplet"] = True

    return row


def _merge_parts(rows):
    """Collapse per-part rows for one measure into a single measure row."""
    merged = {
        "notes": sum(r["notes"] for r in rows),
        "chords": sum(r["chords"] for r in rows),
        "max_chord_span": max(r["max_chord_span"] for r in rows),
        "max_leap": max(r["max_leap"] for r in rows),
        "accidentals": sum(r["accidentals"] for r in rows),
        "rests": sum(r["rests"] for r in rows),
        "per_part_notes": [r["notes"] for r in rows],
    }

    shortest = [r["shortest"] for r in rows if r["shortest"]]
    merged["shortest"] = min(shortest) if shortest else 0

    lows = [r["low"] for r in rows if r["low"] is not None]
    highs = [r["high"] for r in rows if r["high"] is not None]
    if lows and highs:
        merged["range"] = [min(lows), max(highs)]

    # Hand crossing: a lower part reaching above a higher one. Only meaningful
    # for the usual two-stave piano layout.
    if len(rows) == 2:
        rh, lh = rows[0], rows[1]
        if lh["high"] is not None and rh["low"] is not None and lh["high"] > rh["low"]:
            merged["hand_crossing"] = True

    # Polyrhythm: subdivisions that don't nest (3-against-2, 4-against-3).
    subs = [r["shortest"] for r in rows if r["shortest"]]
    if len(subs) == 2 and subs[0] != subs[1]:
        ratio = max(subs) / min(subs)
        if abs(ratio - round(ratio)) > 0.01:
            merged["polyrhythm"] = True

    for key in ("dynamics", "articulations", "ornaments"):
        values = sorted({v for r in rows for v in r.get(key, [])})
        if values:
            merged[key] = values

    for flag in ("grace", "tuplet"):
        if any(r.get(flag) for r in rows):
            merged[flag] = True

    return merged


def _dedupe(entries):
    """Score-level elements repeat once per part on a multi-stave score.
    Collapse to the distinct (measure, value) pairs, in measure order."""
    seen, out = set(), []
    for entry in entries:
        key = tuple(sorted(entry.items(), key=lambda kv: kv[0]))
        if key not in seen:
            seen.add(key)
            out.append(entry)
    return sorted(out, key=lambda e: e["measure"])


def _measure_of(element, default=1):
    """flatten() loses measure context for some elements and reports 0."""
    number = element.measureNumber
    if number:
        return number
    measure = element.getContextByClass("Measure")
    if measure is not None and measure.measureNumber:
        return measure.measureNumber
    return default


def _score_level(score, measures_by_part):
    """Metadata plus the structural signals that drive segmentation."""
    context = {}
    flat = score.flatten()

    if score.metadata:
        if score.metadata.title:
            context["title"] = score.metadata.title
        if score.metadata.composer:
            context["composer"] = score.metadata.composer

    # Signature/tempo *changes* matter as much as the opening values — a key
    # change is a strong section boundary.
    context["keys"] = _dedupe([
        {"measure": _measure_of(k), "key": str(k.asKey())}
        for k in flat.getElementsByClass("KeySignature")
    ])
    context["time_signatures"] = _dedupe([
        {"measure": _measure_of(t), "value": t.ratioString}
        for t in flat.getElementsByClass("TimeSignature")
    ])
    context["tempos"] = _dedupe([
        {
            "measure": _measure_of(m),
            "bpm": int(m.number) if m.number else None,
            "text": m.text or "",
        }
        for m in flat.getElementsByClass("MetronomeMark")
        # An empty marking is noise, not information.
        if m.number or m.text
    ])
    context["clef_changes"] = _dedupe([
        {"measure": _measure_of(c), "clef": c.sign or ""}
        for c in flat.getElementsByClass("Clef")
        if _measure_of(c) > 1
    ])

    context["parts"] = [p.partName or f"Part {i + 1}" for i, p in enumerate(score.parts)]

    context["total_measures"] = len(measures_by_part[0]) if measures_by_part else 0
    # first/last are filled in by extract(), which knows whether the score's own
    # numbering survived the usability check.

    # --- structural signals: the strongest boundary evidence available ---
    repeats, barlines = [], []
    for measure in measures_by_part[0] if measures_by_part else []:
        for bar in measure.recurse().getElementsByClass("Barline"):
            if bar.type in ("double", "final"):
                barlines.append({"measure": measure.measureNumber, "type": bar.type})
            if "Repeat" in bar.classes:
                repeats.append({"measure": measure.measureNumber, "direction": bar.direction})

    context["repeat_barlines"] = _dedupe(repeats)
    context["double_barlines"] = _dedupe(barlines)
    context["voltas"] = _dedupe([
        {
            "measure": min(
                (m.measureNumber for m in b.getSpannedElements() if m.measureNumber is not None),
                default=0,
            ),
            "number": str(b.number),
        }
        for b in flat.getElementsByClass("RepeatBracket")
    ])
    context["repeat_expressions"] = _dedupe([
        {"measure": _measure_of(e), "text": type(e).__name__}
        for e in flat.getElementsByClass("RepeatExpression")
    ])
    context["fermatas"] = sorted(
        {
            n.measureNumber
            for n in flat.notes
            for e in n.expressions
            if type(e).__name__ == "Fermata" and n.measureNumber
        }
    )

    return context


def _derived(rows):
    """Cheap signals computed over the finished table."""
    densities = [r["notes"] for r in rows]
    avg = mean(densities) if densities else 0

    for i, row in enumerate(rows):
        window = densities[max(0, i - 1): i + 2]
        row["rolling_density"] = round(mean(window), 1) if window else 0

        # Novelty: how different is this measure from the previous one? The
        # primary boundary hint the segmenter gets beyond the barline signals.
        if i == 0:
            row["novelty"] = 0
            continue
        prev = rows[i - 1]
        novelty = 0
        if avg:
            novelty += abs(row["notes"] - prev["notes"]) / max(avg, 1)
        if row.get("range") and prev.get("range"):
            novelty += abs(row["range"][0] - prev["range"][0]) / 12
        if row["shortest"] and prev["shortest"] and row["shortest"] != prev["shortest"]:
            novelty += 1
        row["novelty"] = round(novelty, 2)

    # Cadence candidates: a long note or a rest after activity reads as a
    # phrase ending, which is where a section boundary belongs.
    for i, row in enumerate(rows):
        long_note = row["shortest"] >= 2
        breathing = row["rests"] > 0 and row["notes"] <= avg * 0.5
        if long_note or breathing:
            row["cadence_candidate"] = True

    return rows


def extract(score) -> dict:
    """music21 Score -> {score-level metadata, per-measure feature table}.

    Raises TooLongError when the score is too long to plan in one pass.
    """
    measures_by_part = [
        list(part.getElementsByClass("Measure")) for part in score.parts
    ]
    if not measures_by_part or not measures_by_part[0]:
        raise ValueError("score has no measures")

    total = len(measures_by_part[0])
    if total > MAX_MEASURES:
        raise TooLongError(
            f"{total} measures exceeds the {MAX_MEASURES}-measure limit for a single plan"
        )

    # Audiveris output often carries missing or all-zero measure numbers. Left
    # alone that yields a degenerate range and the segmenter is asked to "tile
    # measures 0 to 0", which correctly produces nothing. Fall back to
    # sequential numbering whenever the score's own numbers aren't usable.
    numbers = [m.measureNumber for m in measures_by_part[0]]
    usable = (
        all(n is not None for n in numbers)
        and max(numbers) > 0
        # Contiguous and ascending. Audiveris also emits numbering with GAPS
        # (e.g. 39 measures numbered 0..44), which made the segmenter's
        # instruction "tile measures 0 to 44" unsatisfiable against a table
        # holding only 39 of them — it returned nothing at all. Renumbering
        # guarantees the stated range and the rows always agree.
        and numbers == list(range(numbers[0], numbers[0] + len(numbers)))
    )
    if not usable:
        print(
            f"[features] measure numbering unusable "
            f"({len(numbers)} measures spanning {min(n for n in numbers if n is not None)}-"
            f"{max(n for n in numbers if n is not None)}) - renumbering 1..N"
            if all(n is not None for n in numbers)
            else "[features] measure numbering unusable (missing numbers) - renumbering 1..N"
        )

    rows = []
    for index in range(total):
        per_part = [
            _measure_row(part_measures[index], part_index)
            for part_index, part_measures in enumerate(measures_by_part)
            if index < len(part_measures)
        ]
        if not per_part:
            continue
        row = _merge_parts(per_part)
        # `or` would collapse a pickup measure (number 0) onto m1.
        row["m"] = numbers[index] if usable else index + 1
        rows.append(row)

    score_level = _score_level(score, measures_by_part)
    emitted = [r["m"] for r in rows]
    score_level["first_measure"] = min(emitted)
    score_level["last_measure"] = max(emitted)
    score_level["has_pickup"] = usable and score_level["first_measure"] == 0

    # A degenerate range means every downstream prompt is nonsense. Fail here
    # rather than paying for a fan-out that cannot succeed.
    if score_level["last_measure"] <= score_level["first_measure"]:
        raise ValueError(
            f"unusable measure range {score_level['first_measure']}-{score_level['last_measure']}"
        )

    # The segmenter is told to tile first..last and is given these rows. If the
    # range covers measures the table doesn't contain, that instruction cannot
    # be satisfied and the model returns nothing.
    span = score_level["last_measure"] - score_level["first_measure"] + 1
    if span != len(rows):
        raise ValueError(
            f"measure range {score_level['first_measure']}-{score_level['last_measure']} "
            f"spans {span} measures but the table holds {len(rows)}"
        )

    return {"score": score_level, "measures": _derived(rows)}


def to_prompt_table(features: dict) -> str:
    """Render the feature table compactly. This is the cached prefix, so it
    must be byte-stable across the fan-out — no timestamps, no dict ordering
    surprises, no per-section content."""
    lines = []
    score = features["score"]

    for label, key in (
        ("Title", "title"),
        ("Composer", "composer"),
        ("Total measures", "total_measures"),
    ):
        if score.get(key):
            lines.append(f"{label}: {score[key]}")

    lines.append(f"Parts: {', '.join(score['parts'])}")

    for label, key in (
        ("Keys", "keys"),
        ("Time signatures", "time_signatures"),
        ("Tempos", "tempos"),
        ("Clef changes", "clef_changes"),
        ("Repeat barlines", "repeat_barlines"),
        ("Double barlines", "double_barlines"),
        ("Voltas", "voltas"),
        ("Repeat expressions", "repeat_expressions"),
        ("Fermatas", "fermatas"),
    ):
        if score.get(key):
            lines.append(f"{label}: {score[key]}")

    lines.append("")
    lines.append("Per-measure features (m=measure number):")
    for row in features["measures"]:
        parts = [f"m{row['m']}", f"n={row['notes']}"]
        if row.get("per_part_notes"):
            parts.append(f"hands={row['per_part_notes']}")
        if row.get("range"):
            parts.append(f"range={row['range'][0]}-{row['range'][1]}")
        if row["max_leap"]:
            parts.append(f"leap={row['max_leap']}")
        if row["shortest"]:
            parts.append(f"sub={row['shortest']}")
        if row["chords"]:
            parts.append(f"chords={row['chords']}/span{row['max_chord_span']}")
        if row["accidentals"]:
            parts.append(f"acc={row['accidentals']}")
        parts.append(f"nov={row['novelty']}")
        for flag in ("hand_crossing", "polyrhythm", "cadence_candidate", "grace", "tuplet"):
            if row.get(flag):
                parts.append(flag)
        for key in ("dynamics", "articulations", "ornaments"):
            if row.get(key):
                parts.append(f"{key}={','.join(row[key])}")
        lines.append("  " + " ".join(parts))

    return "\n".join(lines)


def section_slice(features: dict, start: int, end: int) -> str:
    """The measure rows for one section — the only varying part of a fan-out
    prompt, so it goes *after* the cache breakpoint."""
    rows = [r for r in features["measures"] if start <= r["m"] <= end]
    sub = {"score": features["score"], "measures": rows}
    return to_prompt_table(sub).split("Per-measure features (m=measure number):\n", 1)[-1]


def technique_hints(features: dict, start: int, end: int) -> list:
    """Deterministic pre-tagging so the analyst agent confirms rather than
    hunts. Cheap, and it keeps the model honest about what's actually there."""
    rows = [r for r in features["measures"] if start <= r["m"] <= end]
    hints = Counter()
    for row in rows:
        if row["max_leap"] >= 12:
            hints["wide leaps"] += 1
        if row.get("hand_crossing"):
            hints["hand crossing"] += 1
        if row.get("polyrhythm"):
            hints["polyrhythm"] += 1
        if row["max_chord_span"] >= 12:
            hints["wide chord voicing"] += 1
        if row.get("ornaments"):
            hints["trills & ornaments"] += 1
        if row["accidentals"] >= 3:
            hints["chromaticism"] += 1
        if row["shortest"] and row["shortest"] <= 0.25:
            hints["rapid passagework"] += 1
    return [name for name, count in hints.most_common() if count >= 2]
