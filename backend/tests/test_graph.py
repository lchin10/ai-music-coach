"""Graph invariants, no tokens spent.

Run: python tests/test_graph.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.graph import nodes
from app.graph.state import replace_sections
from app.graph.validate import validate


FEATURES = {
    "score": {"total_measures": 16, "parts": ["P1", "P2"], "tempos": [{"measure": 1, "bpm": 100}]},
    "measures": [{"m": i + 1, "notes": 4, "novelty": 0, "shortest": 1,
                  "chords": 0, "max_chord_span": 0, "max_leap": 2,
                  "accidentals": 0, "rests": 0} for i in range(16)],
}

PROFILE = {"piano_level": "intermediate", "years_experience": 5}


def _step(order, tempo=60, checkpoint=False, focus=(1, 8), title="step"):
    return {
        "title": title,
        "description": "d",
        "target_tempo": tempo,
        "drill_type": "checkpoint" if checkpoint else "hands_separate",
        "focus_start_measure": focus[0],
        "focus_end_measure": focus[1],
        "success_criterion": "3 clean run-throughs at 60 bpm",
        "is_checkpoint": checkpoint,
        "unlock_requirement": 0,
        "order_index": order,
    }


def _section(index, start, end, steps):
    return {
        "index": index,
        "title": f"S{index}",
        "start_measure": start,
        "end_measure": end,
        "boundary_rationale": "r",
        "analysis": {"difficulty": 50, "key_challenges": [], "techniques": [],
                     "musical_character": "c", "risk_measures": [],
                     "tempo_floor": 40, "tempo_target": 80},
        "steps": steps,
    }


def _good_plan():
    return [
        _section(0, 1, 8, [_step(0, 50), _step(1, 80, checkpoint=True)]),
        _section(1, 9, 16, [_step(2, 50, focus=(9, 16)),
                            _step(3, 80, checkpoint=True, focus=(9, 16))]),
    ]


def test_clean_plan_passes():
    report = validate(_good_plan(), FEATURES, PROFILE)
    assert report["hard"] == [], report["hard"]


def test_catches_coverage_gap():
    sections = _good_plan()
    sections[1]["start_measure"] = 11  # leaves mm. 9-10 uncovered
    report = validate(sections, FEATURES, PROFILE)
    assert any("gap" in m for m in report["hard"]), report


def test_catches_overlap():
    sections = _good_plan()
    sections[1]["start_measure"] = 7
    report = validate(sections, FEATURES, PROFILE)
    assert any("overlap" in m for m in report["hard"]), report


def test_catches_short_plan():
    sections = [_section(0, 1, 8, [_step(0), _step(1, 80, checkpoint=True)])]
    report = validate(sections, FEATURES, PROFILE)
    assert any("expected 16" in m for m in report["hard"]), report


def test_catches_decreasing_tempo():
    sections = _good_plan()
    sections[0]["steps"] = [_step(0, 90), _step(1, 60, checkpoint=True)]
    report = validate(sections, FEATURES, PROFILE)
    assert any("decreases" in m for m in report["hard"]), report


def test_catches_focus_escaping_section():
    sections = _good_plan()
    sections[0]["steps"][0]["focus_end_measure"] = 14  # section ends at 8
    report = validate(sections, FEATURES, PROFILE)
    assert any("escapes" in m for m in report["hard"]), report


def test_catches_missing_checkpoint():
    sections = _good_plan()
    sections[0]["steps"][-1]["is_checkpoint"] = False
    report = validate(sections, FEATURES, PROFILE)
    assert any("checkpoint" in m for m in report["hard"]), report


def test_catches_uncheckable_success_criterion():
    sections = _good_plan()
    sections[0]["steps"][0]["success_criterion"] = "play it well"
    report = validate(sections, FEATURES, PROFILE)
    assert any("not checkable" in m for m in report["soft"]), report


def test_beginner_needs_hands_separate():
    sections = _good_plan()
    for step in sections[0]["steps"]:
        step["drill_type"] = "checkpoint"
    report = validate(sections, FEATURES, {"piano_level": "beginner"})
    assert any("hands_separate" in m for m in report["soft"]), report


def test_reducer_merges_out_of_order_branches():
    """Fan-out branches finish in any order; the reducer must key on index."""
    merged = replace_sections([], [{"index": 2, "title": "c"}])
    merged = replace_sections(merged, [{"index": 0, "title": "a"}])
    merged = replace_sections(merged, [{"index": 1, "title": "b"}])
    assert [s["title"] for s in merged] == ["a", "b", "c"]


def test_reducer_overwrites_on_revision():
    """A revision pass must replace a section, not append a duplicate."""
    merged = replace_sections([], [{"index": 0, "title": "v1"}, {"index": 1, "title": "keep"}])
    merged = replace_sections(merged, [{"index": 0, "title": "v2"}])
    assert len(merged) == 2
    assert merged[0]["title"] == "v2"
    assert merged[1]["title"] == "keep"


def test_order_index_is_dense_after_validate_node():
    state = {"sections": list(reversed(_good_plan())), "features": FEATURES, "profile": PROFILE}
    result = nodes.validate_plan(state)
    indices = [s["order_index"] for sec in result["sections"] for s in sec["steps"]]
    assert indices == [0, 1, 2, 3], indices
    assert result["validation"]["hard"] == [], result["validation"]["hard"]


def test_critique_skipped_when_validation_clean():
    """Don't pay for a rubber stamp."""
    state = {"validation": {"hard": [], "soft": []}, "revisions": 0}
    assert nodes.critique(state)["critique"]["verdict"] == "approve"


def test_revision_budget_exhausts_to_approve():
    state = {"validation": {"hard": ["x"], "soft": []}, "revisions": nodes.MAX_REVISIONS}
    assert nodes.critique(state)["critique"]["verdict"] == "approve"


def test_route_stops_revising_at_budget():
    at_budget = {"critique": {"verdict": "revise"}, "revisions": nodes.MAX_REVISIONS}
    assert nodes.route_after_critique(at_budget) == "persist"
    under = {"critique": {"verdict": "revise"}, "revisions": 0}
    assert nodes.route_after_critique(under) == "revise"


def test_revise_without_named_sections_falls_through():
    """A critic that says 'revise' but names nothing must not loop forever."""
    state = {"critique": {"verdict": "revise", "section_feedback": []}}
    result = nodes.apply_feedback(state)
    assert result["critique"]["verdict"] == "approve"


def test_fan_out_targets_only_flagged_sections_on_revision():
    state = {
        "boundaries": [{"index": i, "start_measure": 1, "end_measure": 8, "title": "t",
                        "boundary_rationale": "r"} for i in range(3)],
        "features": FEATURES,
        "profile": PROFILE,
        "structural_summary": "s",
        "feedback": {1: "fix it"},
        "sections": [],
    }
    sends = nodes.fan_out(state)
    assert len(sends) == 1
    assert sends[0].arg["boundary"]["index"] == 1


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
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
