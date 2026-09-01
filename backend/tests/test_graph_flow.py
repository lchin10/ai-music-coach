"""End-to-end graph flow with a stubbed model. No tokens spent.

Exercises the parts unit tests can't reach: Send fan-out, the state reducer
across parallel branches, and the critique -> revise -> re-fan-out loop.

Run: python tests/test_graph_flow.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.graph import nodes
from app.graph.build import build

FEATURES = {
    "score": {
        "total_measures": 24, "first_measure": 1, "last_measure": 24,
        "parts": ["RH", "LH"], "tempos": [{"measure": 1, "bpm": 120, "text": ""}],
        "keys": [], "time_signatures": [], "clef_changes": [], "repeat_barlines": [],
        "double_barlines": [], "voltas": [], "repeat_expressions": [], "fermatas": [],
        "has_pickup": False,
    },
    "measures": [{"m": i + 1, "notes": 4, "novelty": 0, "shortest": 1, "chords": 0,
                  "max_chord_span": 0, "max_leap": 2, "accidentals": 0, "rests": 0}
                 for i in range(24)],
}


class StubClient:
    """Records every call and returns canned tool inputs."""

    def __init__(self, critic_verdicts):
        self.calls = []
        self.critic_verdicts = list(critic_verdicts)
        self.messages = self

    def create(self, **kwargs):
        tool = kwargs["tools"][0]["name"]
        user = kwargs["messages"][0]["content"]
        self.calls.append(tool)

        if tool == "define_sections":
            payload = {
                "structural_summary": "binary form",
                "sections": [
                    {"title": "A", "start_measure": 1, "end_measure": 12,
                     "boundary_rationale": "double barline at m.12"},
                    {"title": "B", "start_measure": 13, "end_measure": 24,
                     "boundary_rationale": "final barline"},
                ],
            }
        elif tool == "analyze_section":
            payload = {
                "difficulty": 55, "key_challenges": ["LH leap at m.5"],
                "techniques": ["wide leaps"], "musical_character": "lyrical",
                "risk_measures": [5], "tempo_floor": 60, "tempo_target": 100,
            }
        elif tool == "design_drills":
            start = 1 if "measures 1-12" in user else 13
            end = start + 11
            payload = {"steps": [
                {"title": "hands separate", "description": "d", "target_tempo": 60,
                 "drill_type": "hands_separate", "focus_start_measure": start,
                 "focus_end_measure": end,
                 "success_criterion": "2 clean runs at 60 bpm",
                 "is_checkpoint": False, "unlock_requirement": 0},
                {"title": "checkpoint", "description": "d", "target_tempo": 100,
                 "drill_type": "checkpoint", "focus_start_measure": start,
                 "focus_end_measure": end,
                 "success_criterion": "3 clean runs at 100 bpm",
                 "is_checkpoint": True, "unlock_requirement": 60},
            ]}
        elif tool == "review_plan":
            verdict = self.critic_verdicts.pop(0) if self.critic_verdicts else "approve"
            payload = {
                "verdict": verdict,
                "reasoning": "stub",
                "section_feedback": (
                    [{"section_index": 0, "feedback": "narrow the loop"}]
                    if verdict == "revise" else []
                ),
            }
        else:
            raise AssertionError(f"unexpected tool {tool}")

        return _Response(tool, payload)


class _Block:
    def __init__(self, name, payload):
        self.type = "tool_use"
        self.name = name
        self.input = payload


class _Usage:
    input_tokens = 0
    output_tokens = 0
    cache_read_input_tokens = 0


class _Response:
    def __init__(self, name, payload):
        self.content = [_Block(name, payload)]
        self.usage = _Usage()


def run(critic_verdicts):
    stub = StubClient(critic_verdicts)
    nodes._client = stub
    state = build().invoke(
        {"piece_id": "p1", "user_id": "u1", "profile": {"piano_level": "intermediate"},
         "features": FEATURES, "revisions": 0},
        {"configurable": {"thread_id": "t"}, "recursion_limit": 50},
    )
    return state, stub


def test_happy_path_produces_tiling_plan():
    # Validation is clean, so the critic is never called at all.
    state, stub = run([])
    sections = state["sections"]
    assert len(sections) == 2, sections
    assert sections[0]["start_measure"] == 1
    assert sections[-1]["end_measure"] == 24
    assert stub.calls.count("define_sections") == 1
    assert stub.calls.count("analyze_section") == 2, stub.calls
    assert stub.calls.count("design_drills") == 2, stub.calls
    assert "review_plan" not in stub.calls, "clean plan should skip the critic"


def test_order_index_dense_across_parallel_branches():
    state, _ = run([])
    indices = [s["order_index"] for sec in state["sections"] for s in sec["steps"]]
    assert indices == [0, 1, 2, 3], indices


def test_revision_reruns_only_the_flagged_section():
    """Forcing a revise must re-run one section, not the whole fan-out."""
    original = nodes.critique

    def always_revise_once(state):
        if state.get("revisions", 0) == 0:
            return {"critique": {"verdict": "revise", "reasoning": "stub",
                                 "section_feedback": [
                                     {"section_index": 0, "feedback": "narrow it"}]}}
        return {"critique": {"verdict": "approve", "reasoning": "ok",
                             "section_feedback": []}}

    nodes.critique = always_revise_once
    try:
        state, stub = run([])
    finally:
        nodes.critique = original

    # 2 branches on the first pass + 1 on the revision.
    assert stub.calls.count("design_drills") == 3, stub.calls
    # The analyst is skipped on revision — the analysis was not what was criticised.
    assert stub.calls.count("analyze_section") == 2, stub.calls
    assert state["revisions"] == 1
    assert len(state["sections"]) == 2, "revision must not duplicate sections"


def test_revision_budget_terminates():
    original = nodes.critique
    nodes.critique = lambda s: (
        {"critique": {"verdict": "approve", "reasoning": "budget",
                      "section_feedback": []}}
        if s.get("revisions", 0) >= nodes.MAX_REVISIONS
        else {"critique": {"verdict": "revise", "reasoning": "again",
                           "section_feedback": [{"section_index": 0, "feedback": "f"}]}}
    )
    try:
        state, stub = run([])
    finally:
        nodes.critique = original

    assert state["revisions"] == nodes.MAX_REVISIONS
    assert len(state["sections"]) == 2


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
