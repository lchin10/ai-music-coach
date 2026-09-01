"""Graph nodes.

Anthropic SDK is called directly — LangGraph orchestrates, it does not wrap
the model. That keeps adaptive thinking, effort, cache_control and strict
tools available, none of which survive a LangChain model abstraction.
"""

import json
import os
import tempfile
import time

import anthropic

from app.graph import features as feat
from app.graph import prompts
from app.graph.validate import summarize, validate

MODEL = "claude-opus-5"
MAX_REVISIONS = 2
MAX_SECTIONS = 30  # the fan-out is the cost driver — N sections is 2N calls

_client = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _dump_payload(name: str, kwargs: dict):
    """Write a rejected request to a temp file for inspection."""
    try:
        path = os.path.join(
            tempfile.gettempdir(), f"graph_reject_{name}_{int(time.time())}.json"
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(kwargs, f, indent=1, default=str, ensure_ascii=False)

        system_chars = sum(len(b["text"]) for b in kwargs.get("system", []))
        user = kwargs["messages"][0]["content"]
        print(
            f"[graph] payload dumped to {path} "
            f"(system={system_chars} chars, user={len(user)} chars, "
            f"max_tokens={kwargs.get('max_tokens')})"
        )
    except Exception as e:
        print(f"[graph] could not dump payload: {e}")


def _call(system_prompt, cached_prefix, user_content, tool, effort, thinking=False):
    """One tool-forced call.

    The cache breakpoint sits at the end of `cached_prefix`, which is byte
    identical across every fan-out branch. Anything varying per branch must
    go in `user_content`, after the breakpoint, or the cache never hits.
    """
    kwargs = {
        "model": MODEL,
        "max_tokens": 8192,
        "system": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": cached_prefix,
                "cache_control": {"type": "ephemeral"},
            },
        ],
        "output_config": {"effort": effort},
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": tool["name"]},
        "messages": [{"role": "user", "content": user_content}],
    }
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}

    try:
        response = client().messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        # The API's 400 body is often just "Invalid request data", which says
        # nothing about which field it disliked. Dump the exact payload so the
        # failure is diagnosable from one occurrence instead of a re-run.
        print(f"[graph] {tool['name']} rejected ({e.status_code}): {e}")
        _dump_payload(tool["name"], kwargs)
        raise

    usage = response.usage
    print(
        f"[graph] {tool['name']}: in={usage.input_tokens} out={usage.output_tokens} "
        f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)}"
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return block.input

    raise RuntimeError(f"{tool['name']} returned no tool_use block")


# --------------------------------------------------------------------------
# Deterministic nodes
# --------------------------------------------------------------------------


def extract_features(state):
    # `features` is populated by the caller from the parsed score; this node
    # exists so the cached prefix is built exactly once per run.
    return {}


def cached_prefix(state) -> str:
    return (
        "Here is the complete score analysis. It is identical for every "
        "question you will be asked about this piece.\n\n"
        + feat.to_prompt_table(state["features"])
    )


# --------------------------------------------------------------------------
# 1. Segmenter
# --------------------------------------------------------------------------


def segment(state):
    score = state["features"]["score"]
    total = score["total_measures"]
    first = score.get("first_measure", 1)
    last = score.get("last_measure") or total

    pickup = (
        "\nThis piece begins with a pickup measure numbered 0 — include it in "
        "the first section.\n"
        if score.get("has_pickup")
        else ""
    )

    result = _call(
        prompts.SEGMENT_SYSTEM,
        cached_prefix(state),
        f"Divide this {total}-measure piece into practice sections.\n"
        f"{prompts.level_line(state['profile'])}\n"
        f"{pickup}\n"
        "Let the music decide how many sections there are. Sections must tile "
        f"measures {first} to {last} with no gaps or overlaps.",
        prompts.SEGMENT_TOOL,
        effort="high",
        thinking=True,
    )

    print(
        f"[graph] segmenter returned {len(result['sections'])} sections "
        f"for measures {first}-{last}"
    )
    if not result["sections"]:
        # Silently returning nothing here used to produce an empty fan-out, an
        # empty plan, and a confusing PostgREST error at insert time.
        raise RuntimeError(
            f"segmenter returned no sections for measures {first}-{last}"
        )

    sections = result["sections"][:MAX_SECTIONS]
    if len(result["sections"]) > MAX_SECTIONS:
        print(
            f"[graph] WARNING: segmenter returned {len(result['sections'])} sections, "
            f"capped at {MAX_SECTIONS}"
        )
        # Keep the plan tiling: stretch the last kept section to the end.
        sections[-1] = {**sections[-1], "end_measure": last}

    return {
        "structural_summary": result["structural_summary"],
        "boundaries": [{**s, "index": i} for i, s in enumerate(sections)],
    }


def fan_out(state):
    """Conditional edge: one Send per section, executed in parallel."""
    from langgraph.types import Send

    targets = state.get("feedback") or {}
    boundaries = state["boundaries"]

    # A revision pass only re-runs the sections the critic flagged.
    if targets:
        boundaries = [b for b in boundaries if b["index"] in targets]

    return [
        Send(
            "analyze_section",
            {
                "boundary": boundary,
                "features": state["features"],
                "profile": state["profile"],
                "structural_summary": state["structural_summary"],
                "feedback": targets.get(boundary["index"]),
                "existing": next(
                    (s for s in state.get("sections", []) if s["index"] == boundary["index"]),
                    None,
                ),
            },
        )
        for boundary in boundaries
    ]


# --------------------------------------------------------------------------
# 2 + 3. Section analyst and drill designer (fan-out branch)
# --------------------------------------------------------------------------


def analyze_section(branch):
    """Runs analysis then drills for one section, in one branch."""
    boundary = branch["boundary"]
    start, end = boundary["start_measure"], boundary["end_measure"]
    prefix = (
        "Here is the complete score analysis. It is identical for every "
        "question you will be asked about this piece.\n\n"
        + feat.to_prompt_table(branch["features"])
    )
    level = prompts.level_line(branch["profile"])

    # On a revision pass the analysis is still valid — only the drills were
    # criticised — so skip the analyst call and save a round trip.
    existing = branch.get("existing")
    if existing and branch.get("feedback"):
        analysis = existing["analysis"]
    else:
        hints = feat.technique_hints(branch["features"], start, end)
        analysis = _call(
            prompts.ANALYZE_SYSTEM,
            prefix,
            f"Analyse the section '{boundary['title']}', measures {start}-{end}.\n"
            f"{level}\n"
            f"Form context: {branch['structural_summary']}\n"
            f"Why this section was cut here: {boundary['boundary_rationale']}\n"
            f"Deterministic technique hints (confirm or reject these): "
            f"{hints or 'none detected'}\n\n"
            f"Measure rows for this section:\n"
            f"{feat.section_slice(branch['features'], start, end)}",
            prompts.ANALYZE_TOOL,
            effort="medium",
        )

    drill_request = (
        f"Write the practice steps for '{boundary['title']}', measures {start}-{end}.\n"
        f"{level}\n\n"
        f"Section analysis:\n"
        f"  difficulty: {analysis['difficulty']}/100 for this student\n"
        f"  challenges: {analysis['key_challenges']}\n"
        f"  techniques: {analysis['techniques']}\n"
        f"  character: {analysis['musical_character']}\n"
        f"  risk measures: {analysis['risk_measures']}\n"
        f"  tempo floor {analysis['tempo_floor']} -> target {analysis['tempo_target']} bpm\n\n"
        f"Focus ranges must lie within {start}-{end}."
    )

    if branch.get("feedback"):
        drill_request += (
            f"\n\nA reviewer rejected your previous steps for this section:\n"
            f"{branch['feedback']}\n"
            f"Address that feedback directly."
        )

    drills = _call(
        prompts.DRILLS_SYSTEM,
        prefix,
        drill_request,
        prompts.DRILLS_TOOL,
        effort="medium",
    )

    return {
        "sections": [
            {
                "index": boundary["index"],
                "title": boundary["title"],
                "start_measure": start,
                "end_measure": end,
                "boundary_rationale": boundary["boundary_rationale"],
                "analysis": analysis,
                "steps": drills["steps"],
            }
        ]
    }


# --------------------------------------------------------------------------
# 5. Validator
# --------------------------------------------------------------------------


def validate_plan(state):
    # order_index is assigned here, after the fan-out has merged, because a
    # branch cannot know its position in the finished plan.
    ordered = sorted(state["sections"], key=lambda s: s["start_measure"])
    counter = 0
    for section in ordered:
        for step in section["steps"]:
            step["order_index"] = counter
            counter += 1

    return {
        "sections": ordered,
        "validation": validate(ordered, state["features"], state["profile"]),
    }


# --------------------------------------------------------------------------
# 6. Critic
# --------------------------------------------------------------------------


def critique(state):
    report = state["validation"]

    # Nothing to review and nothing flagged — don't pay for a rubber stamp.
    if not report["hard"] and not report["soft"]:
        return {"critique": {"verdict": "approve", "reasoning": "clean validation"}}

    if state.get("revisions", 0) >= MAX_REVISIONS:
        return {
            "critique": {
                "verdict": "approve",
                "reasoning": "revision budget exhausted; shipping best effort",
            }
        }

    plan_text = "\n".join(
        f"[{s['index']}] {s['title']} (mm. {s['start_measure']}-{s['end_measure']}) "
        f"— cut because: {s['boundary_rationale']}\n"
        f"    difficulty {s['analysis']['difficulty']}, "
        f"challenges: {s['analysis']['key_challenges']}\n"
        + "\n".join(
            f"    {i + 1}. [{st['drill_type']}] {st['title']} @ {st['target_tempo']}bpm "
            f"(mm. {st['focus_start_measure']}-{st['focus_end_measure']}) "
            f"— {st['success_criterion']}"
            for i, st in enumerate(s["steps"])
        )
        for s in state["sections"]
    )

    try:
        result = _call(
            prompts.CRITIQUE_SYSTEM,
            cached_prefix(state),
            f"Review this practice plan.\n"
            f"{prompts.level_line(state['profile'])}\n"
            f"Form: {state['structural_summary']}\n\n"
            f"{plan_text}\n\n"
            f"{summarize(report)}",
            prompts.CRITIQUE_TOOL,
            effort="high",
            thinking=True,
        )
    except Exception as e:
        # The critic is an optional quality gate, and by this point the plan
        # has already passed the deterministic validator and cost N sections
        # of fan-out. Throwing all of that away over a failed review — and
        # falling back to the 3-section deterministic plan — is far worse than
        # shipping an unreviewed plan.
        print(f"[graph] critique failed, shipping unreviewed plan: {e}")
        return {"critique": {"verdict": "approve", "reasoning": f"critique unavailable: {e}"}}

    return {"critique": result}


def route_after_critique(state):
    verdict = state["critique"]["verdict"]
    if verdict == "revise" and state.get("revisions", 0) < MAX_REVISIONS:
        return "revise"
    return "persist"


def apply_feedback(state):
    feedback = {
        item["section_index"]: item["feedback"]
        for item in state["critique"].get("section_feedback", [])
    }
    if not feedback:
        # Critic asked for a revision but named no section — nothing actionable.
        return {"critique": {**state["critique"], "verdict": "approve"}, "feedback": {}}
    return {"feedback": feedback, "revisions": 1}


def clear_feedback(state):
    return {"feedback": {}}
