"""Ladder and scheduler invariants. No tokens, no database.

Run: python tests/test_ladder.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.coach import ladder, remediate, scheduler


def section(sid="s1", start=1, end=16, risk=(), techniques=(), floor=50, target=100):
    return {
        "id": sid,
        "title": f"Section {sid}",
        "start_measure": start,
        "end_measure": end,
        "analysis_data": {
            "risk_measures": list(risk),
            "techniques": list(techniques),
            "tempo_floor": floor,
            "tempo_target": target,
            "key_challenges": [],
        },
    }


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Ladder
# --------------------------------------------------------------------------


def test_chunks_tile_the_section_exactly():
    for end in range(3, 40):
        sec = section(end=end)
        chunks = [
            (s["focus_start_measure"], s["focus_end_measure"])
            for s in ladder.build(sec) if s["stage"] == "notes"
        ]
        assert chunks[0][0] == 1, chunks
        assert chunks[-1][1] == end, (end, chunks)
        for (_, prev_end), (nxt_start, _) in zip(chunks, chunks[1:]):
            assert nxt_start == prev_end + 1, (end, chunks)


def test_no_orphan_single_bar_at_the_end():
    # 5 bars at chunk size 2 would leave m.5 alone; it joins the chunk before.
    chunks = [
        (s["focus_start_measure"], s["focus_end_measure"])
        for s in ladder.build(section(end=7)) if s["stage"] == "notes"
    ]
    assert chunks == [(1, 2), (3, 4), (5, 7)], chunks


def test_metronome_is_locked_until_the_notes_are_learned():
    steps = ladder.build(section(risk=[5], techniques=["polyrhythm"]))
    for s in steps:
        if s["stage"] in ("notes", "thread"):
            assert s["metronome"] == ladder.METRONOME_OFF, s
        if s["stage"] in ("rhythm", "tempo"):
            assert s["metronome"] == ladder.METRONOME_REQUIRED, s


def test_every_focus_range_stays_inside_the_section():
    sec = section(start=9, end=25, risk=[12, 20], techniques=["wide leaps"])
    for s in ladder.build(sec):
        assert 9 <= s["focus_start_measure"] <= s["focus_end_measure"] <= 25, s


def test_rhythm_only_where_a_risk_measure_meets_a_rhythmic_technique():
    leaps = ladder.build(section(risk=[5], techniques=["wide leaps"]))
    assert not any(s["stage"] == "rhythm" for s in leaps)
    assert any(s["stage"] == "technique" for s in leaps)

    triplets = ladder.build(section(risk=[5], techniques=["polyrhythm"]))
    assert any(s["stage"] == "rhythm" for s in triplets)


def test_pair_tree_terminates_at_the_whole_section():
    for end in (8, 9, 16, 17, 30):
        steps = ladder.build(section(end=end))
        # The top merge is the section itself, so `pair` stops short of it and
        # `section` covers the full range exactly once.
        whole = [s for s in steps if s["stage"] == "section"]
        assert len(whole) == 1, (end, whole)
        assert (whole[0]["focus_start_measure"], whole[0]["focus_end_measure"]) == (1, end)
        for s in steps:
            if s["stage"] == "pair":
                assert (s["focus_start_measure"], s["focus_end_measure"]) != (1, end), end


def test_keys_are_unique_and_deterministic():
    """Progress hangs off these keys — a collision or a drift orphans it."""
    sec = section(risk=[3, 4, 11], techniques=["polyrhythm", "wide leaps"])
    first = ladder.build(sec)
    second = ladder.build(sec)
    keys = [s["key"] for s in first]
    assert len(keys) == len(set(keys)), [k for k in keys if keys.count(k) > 1]
    assert keys == [s["key"] for s in second]


def test_tempo_rungs_stop_at_target():
    steps = ladder.build(section(floor=50, target=100))
    rungs = [s["target_tempo"] for s in steps if s["stage"] == "tempo"]
    assert rungs == [60, 80, 100], rungs


def test_tiny_and_huge_sections_both_produce_a_sane_ladder():
    tiny = ladder.build(section(start=1, end=4))
    huge = ladder.build(section(start=1, end=60))
    for steps in (tiny, huge):
        stages = {s["stage"] for s in steps}
        assert {"notes", "thread", "section", "tempo"} <= stages, stages
    assert len(tiny) < len(huge)


def test_dense_risk_forces_single_bar_chunks():
    steps = ladder.build(section(end=16, risk=[3, 4]))
    chunk = [s for s in steps if s["stage"] == "notes"
             and s["focus_start_measure"] == 3]
    assert chunk[0]["focus_end_measure"] == 3, chunk


def test_authored_prose_is_borrowed_by_the_matching_stage():
    authored = [{
        "drill_type": "tempo_building",
        "focus_start_measure": 1,
        "focus_end_measure": 16,
        "description": "Ladder 60-72-84 watching the LH thumb.",
    }]
    steps = ladder.build(section(), authored)
    tempo = [s for s in steps if s["stage"] == "tempo"][0]
    assert "LH thumb" in tempo["description"], tempo["description"]


# --------------------------------------------------------------------------
# Mastery
# --------------------------------------------------------------------------


def test_report_and_tempo_move_the_score():
    assert scheduler.score_attempt("nailed", 100, 100) == 100
    assert scheduler.score_attempt("struggling", 100, 100) == 25
    assert scheduler.score_attempt("nailed", 50, 100) == 75
    # An untimed stage is not punished for having no tempo.
    assert scheduler.score_attempt("nailed") == 100


def test_streak_resets_on_anything_but_nailed():
    assert scheduler.bump_streak(3, "nailed") == 4
    assert scheduler.bump_streak(3, "shaky") == 0
    assert scheduler.bump_streak(3, "struggling") == 0


def test_mastery_cannot_exceed_the_stage_ceiling():
    """Nailing every 2-bar chunk is not mastering the passage."""
    steps = ladder.build(section())
    nailed = {s["key"] for s in steps if s["stage"] == "notes"}
    ceiling = scheduler.ceiling_for(steps, nailed)
    assert ceiling == 25, ceiling

    mastery = 0
    for _ in range(20):
        mastery, _ = scheduler.update_mastery(mastery, 0, 100, ceiling)
    assert mastery == 25, mastery


def test_ceiling_rises_as_the_ladder_is_climbed():
    steps = ladder.build(section())
    nailed = set()
    seen = []
    for stage in ladder.STAGES:
        nailed |= {s["key"] for s in steps if s["stage"] == stage}
        seen.append(scheduler.ceiling_for(steps, nailed))
    assert seen == sorted(seen), seen
    assert seen[-1] == 100, seen


def test_decay_creates_review_debt_at_streak_zero_but_not_at_streak_five():
    stale = NOW - timedelta(days=5)
    assert scheduler.decayed(90, 0, stale, NOW) < scheduler.REVIEW_FLOOR
    assert scheduler.decayed(90, 5, stale, NOW) >= scheduler.REVIEW_FLOOR


# --------------------------------------------------------------------------
# Scheduler
# --------------------------------------------------------------------------


def _world(count=3, **kw):
    sections = [
        section(sid=f"s{i}", start=1 + i * 16, end=16 + i * 16, **kw)
        for i in range(count)
    ]
    ladders = {s["id"]: ladder.build(s) for s in sections}
    return sections, ladders


def _attempts(steps, when=NOW, report="nailed"):
    return [{"section_id": s["section_id"], "step_key": s["key"], "stage": s["stage"],
             "self_report": report, "created_at": when} for s in steps]


def test_first_action_is_the_first_notes_chunk():
    sections, ladders = _world()
    action = scheduler.next_action(sections, ladders, [], {}, now=NOW)
    assert action["kind"] == "advance"
    assert action["step"]["stage"] == "notes"
    assert action["step"]["metronome"] == ladder.METRONOME_OFF


def test_remediation_outranks_resume():
    sections, ladders = _world()
    done = _attempts(ladders["s0"][:1])
    queued = [{"key": "rem-1", "section_id": "s0", "stage": "notes",
               "focus_start_measure": 1, "focus_end_measure": 1,
               "target_tempo": None, "metronome": "off", "title": "t",
               "description": "d", "source": "remediation"}]
    action = scheduler.next_action(sections, ladders, done, {}, queued, now=NOW)
    assert action["kind"] == "remediation", action


def test_resume_returns_to_the_section_last_touched():
    sections, ladders = _world()
    done = _attempts(ladders["s0"][:3])
    action = scheduler.next_action(sections, ladders, done, {}, now=NOW)
    assert action["kind"] == "resume"
    assert action["step"]["key"] == ladders["s0"][3]["key"]


def test_review_outranks_advance_and_re_enters_at_the_section_stage():
    sections, ladders = _world()
    done = _attempts(ladders["s0"], when=NOW - timedelta(days=30))
    mastery = {"s0": {"mastery": 95, "streak": 0,
                      "last_practiced_at": NOW - timedelta(days=30)}}
    action = scheduler.next_action(sections, ladders, done, mastery, now=NOW)
    assert action["kind"] == "review", action
    assert action["step"]["stage"] == "section", action["step"]


def test_integration_fires_for_adjacent_sections_only():
    sections, ladders = _world()
    done = _attempts(ladders["s0"]) + _attempts(ladders["s2"])
    action = scheduler.next_action(sections, ladders, done, {}, now=NOW)
    # s0 and s2 are both finished but are NOT adjacent, so the next thing is
    # s1's own work, never a join across the gap.
    assert action["kind"] != "integration", action

    done += _attempts(ladders["s1"])
    action = scheduler.next_action(sections, ladders, done, {}, now=NOW)
    assert action["kind"] == "integration", action
    assert action["step"]["focus_start_measure"] < 17 <= action["step"]["focus_end_measure"]


def test_a_section_is_locked_until_its_predecessor_is_paired_up():
    sections, ladders = _world()
    nailed = {s["key"] for s in ladders["s0"] if s["stage"] in ("notes", "thread")}
    assert "s1" in scheduler.locked_sections(sections, ladders, nailed)

    through_pair = {
        s["key"] for s in ladders["s0"]
        if ladder.STAGES.index(s["stage"]) <= ladder.STAGES.index("pair")
    }
    assert "s1" not in scheduler.locked_sections(sections, ladders, through_pair)


def test_everything_at_tempo_ends_in_a_run_through():
    sections, ladders = _world(count=2)
    done = _attempts(ladders["s0"]) + _attempts(ladders["s1"])
    done += [{"section_id": "s1", "step_key": "s0+s1:integration",
              "stage": "integration", "self_report": "nailed", "created_at": NOW}]
    action = scheduler.next_action(sections, ladders, done, {}, now=NOW)
    assert action["kind"] == "run_through", action


# --------------------------------------------------------------------------
# Remediation
# --------------------------------------------------------------------------


def test_narrow_returns_something_easier_for_every_stage():
    sec = section(risk=[5], techniques=["polyrhythm", "wide leaps"])
    steps = ladder.build(sec)
    stages = {s["stage"] for s in steps}
    assert len(stages) >= 6, stages

    for step in steps:
        drills = remediate.narrow(step, sec)
        assert drills, step["stage"]
        for d in drills:
            span = d["focus_end_measure"] - d["focus_start_measure"]
            original = step["focus_end_measure"] - step["focus_start_measure"]
            slower = (d["target_tempo"] or 0) < (step["target_tempo"] or 10**6)
            assert span < original or slower or d["stage"] != step["stage"], (step, d)
            assert sec["start_measure"] <= d["focus_start_measure"], d
            assert d["focus_end_measure"] <= sec["end_measure"], d
            assert d["target_tempo"] is None or d["target_tempo"] >= remediate.TEMPO_MIN, d


def test_narrow_never_puts_a_metronome_on_the_notes_stage():
    sec = section()
    notes = [s for s in ladder.build(sec) if s["stage"] == "notes"][0]
    for d in remediate.narrow(notes, sec):
        assert d["metronome"] == ladder.METRONOME_OFF, d


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ok   {test.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {test.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERR  {test.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
