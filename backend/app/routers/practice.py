"""The practice session runtime.

Only `/struggling` can ever call a model, and only on a second tap. Every
other endpoint is one round of queries plus arithmetic — tapping "Nailed it"
has to advance instantly, so nothing on that path is allowed to be slow.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import current_user, own_piece, own_session
from app.coach import ladder, remediate, scheduler
from app.db import client as db

router = APIRouter(prefix="/practice", tags=["practice"])

# Upper bounds on client-reported numbers, so one bad request can't poison
# mastery or session totals.
MAX_STEP_SECONDS = 4 * 60 * 60
MAX_SESSION_SECONDS = 24 * 60 * 60
MAX_BPM = 400


def _now():
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _remediation_steps(rows: list) -> list:
    """plan_steps rows with source='remediation', shaped like ladder steps."""
    return [{
        "key": row["id"],
        "section_id": row["section_id"],
        "stage": row.get("stage") or "technique",
        "focus_start_measure": row.get("focus_start_measure"),
        "focus_end_measure": row.get("focus_end_measure"),
        # plan_steps.target_tempo is not nullable, so an untimed drill (a
        # `notes` breakdown) is stored as 0 and has to come back as None or
        # the UI offers a 0 bpm metronome.
        "target_tempo": row.get("target_tempo") or None,
        "metronome": row.get("metronome") or ladder.METRONOME_OPTIONAL,
        "title": row["title"],
        # plan_steps stores flat text, so the structure is rebuilt on read.
        # A stored breakdown is one point; the title already leads it.
        "instructions": [{"lead": "", "detail": row.get("description") or ""}],
        "description": row.get("description") or "",
        "source": "remediation",
    } for row in rows]


def load(user_id: str, piece_id: str) -> dict:
    """Everything the scheduler needs, in four queries."""
    client = db()
    sections = (
        client.table("sections").select("*")
        .eq("piece_id", piece_id).order("start_measure").execute()
    ).data or []

    section_ids = [s["id"] for s in sections]
    steps, attempts, mastery_rows = [], [], []

    if section_ids:
        steps = (
            client.table("plan_steps").select("*")
            .in_("section_id", section_ids).order("order_index").execute()
        ).data or []
        attempts = (
            client.table("step_attempts").select("*")
            .eq("user_id", user_id).in_("section_id", section_ids)
            .order("created_at").execute()
        ).data or []
        mastery_rows = (
            client.table("section_mastery").select("*")
            .eq("user_id", user_id).in_("section_id", section_ids).execute()
        ).data or []

    authored = {}
    for step in steps:
        if step.get("source", "plan") == "plan":
            authored.setdefault(step["section_id"], []).append(step)

    return {
        "sections": sections,
        "ladders": {s["id"]: ladder.build(s, authored.get(s["id"], [])) for s in sections},
        "attempts": attempts,
        "mastery": {m["section_id"]: m for m in mastery_rows},
        "remediation": _remediation_steps(
            [s for s in steps if s.get("source") == "remediation"]
        ),
    }


def state(world: dict, session_id: Optional[str] = None) -> dict:
    """The whole UI payload: what to do next, and where that sits."""
    action = scheduler.next_action(
        world["sections"], world["ladders"], world["attempts"],
        world["mastery"], world["remediation"], _now(),
    )

    nailed = {a["step_key"] for a in world["attempts"] if a.get("self_report") == "nailed"}
    visited = {a["step_key"] for a in world["attempts"]}
    locked = scheduler.locked_sections(world["sections"], world["ladders"], nailed)

    sections = []
    for section in world["sections"]:
        steps = world["ladders"][section["id"]]
        row = world["mastery"].get(section["id"], {})
        done = scheduler.completed_stage(steps, nailed)
        sections.append({
            "id": section["id"],
            "title": section["title"],
            "start_measure": section["start_measure"],
            "end_measure": section["end_measure"],
            "mastery": row.get("mastery", 0),
            "reached_stage": done,
            "complete": done == "tempo",
            "locked": section["id"] in locked,
            # The rungs ride along trimmed — key, label and status only. The
            # full step (instructions and all) is fetched by /practice/step
            # when one is actually opened, so the rail stays cheap to send on
            # every tap.
            "stages": ladder.stage_progress(steps, nailed, visited),
        })

    return {"session_id": session_id, "action": action, "sections": sections}


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


def _section(world: dict, section_id: str) -> dict:
    """A section of the loaded piece, or 404 — so an attempt can't be filed
    against a section from some other piece."""
    section = next((s for s in world["sections"] if s["id"] == section_id), None)
    if not section:
        raise HTTPException(404, "Section not found")
    return section


class StartBody(BaseModel):
    piece_id: str


@router.post("/session/start")
async def start(body: StartBody, user_id: str = Depends(current_user)):
    own_piece(user_id, body.piece_id)
    session_id = str(uuid.uuid4())
    db().table("practice_sessions").insert({
        "id": session_id, "user_id": user_id, "piece_id": body.piece_id,
    }).execute()
    return state(load(user_id, body.piece_id), session_id)


@router.get("/next")
async def next_step(piece_id: str, session_id: str = None,
                    user_id: str = Depends(current_user)):
    own_piece(user_id, piece_id)
    if session_id is not None:
        own_session(user_id, session_id, piece_id)
    return state(load(user_id, piece_id), session_id)


@router.get("/step")
async def one_step(piece_id: str, step_key: str, user_id: str = Depends(current_user)):
    """The full rung behind a sidebar entry.

    The rail only carries labels and status; the instructions are fetched when
    a student actually jumps to a rung, which is rare compared to tapping
    through the ladder in order.
    """
    own_piece(user_id, piece_id)
    world = load(user_id, piece_id)
    for steps in list(world["ladders"].values()) + [world["remediation"]]:
        for step in steps:
            if step["key"] == step_key:
                return {"step": step}
    return {"error": "step not found"}


class AttemptBody(BaseModel):
    session_id: str
    piece_id: str
    section_id: str
    step_key: str
    stage: str
    self_report: Literal["nailed", "shaky"]
    tempo_reached: Optional[int] = Field(None, ge=1, le=MAX_BPM)
    target_tempo: Optional[int] = Field(None, ge=0, le=MAX_BPM)
    metronome_on: bool = False
    seconds: int = Field(0, ge=0, le=MAX_STEP_SECONDS)


def _record(world, user_id, section_id, rows):
    """Insert attempts and roll the section's mastery forward.

    Mastery is capped by how far up the ladder the student has actually got,
    so nailing twenty two-bar chunks cannot report the section as learned.
    """
    client = db()
    # Underscore keys ride along for scoring but are not columns.
    client.table("step_attempts").insert(
        [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows]
    ).execute()

    world["attempts"] = list(world["attempts"]) + rows
    nailed = {a["step_key"] for a in world["attempts"] if a.get("self_report") == "nailed"}
    steps = world["ladders"].get(section_id, [])
    ceiling = scheduler.ceiling_for(steps, nailed)

    previous = world["mastery"].get(section_id, {})
    value = previous.get("mastery", 0)
    streak = previous.get("streak", 0)
    for row in rows:
        sample = scheduler.score_attempt(
            row.get("self_report"), row.get("tempo_reached"), row.get("_target_tempo")
        )
        value, _ = scheduler.update_mastery(value, streak, sample, ceiling)
        streak = scheduler.bump_streak(streak, row.get("self_report"))

    updated = {
        "user_id": user_id,
        "section_id": section_id,
        "mastery": value,
        "streak": streak,
        "reached_stage": scheduler.completed_stage(steps, nailed) or "notes",
        "times_reviewed": previous.get("times_reviewed", 0) + 1,
        "last_practiced_at": _now().isoformat(),
    }
    client.table("section_mastery").upsert(updated).execute()
    world["mastery"][section_id] = updated
    return updated


@router.post("/attempt")
async def attempt(body: AttemptBody, user_id: str = Depends(current_user)):
    own_piece(user_id, body.piece_id)
    own_session(user_id, body.session_id, body.piece_id)
    world = load(user_id, body.piece_id)
    _section(world, body.section_id)
    row = {
        "id": str(uuid.uuid4()),
        "session_id": body.session_id,
        "user_id": user_id,
        "section_id": body.section_id,
        "step_key": body.step_key,
        "stage": body.stage,
        "seconds": body.seconds,
        "tempo_reached": body.tempo_reached,
        "metronome_on": body.metronome_on,
        "self_report": body.self_report,
    }
    # Carried alongside the row for scoring, but not a column.
    updated = _record(world, user_id, body.section_id,
                      [dict(row, _target_tempo=body.target_tempo)])

    result = state(world, body.session_id)
    result["mastery"] = updated["mastery"]
    result["reached_stage"] = updated["reached_stage"]
    return result


class SkipBody(BaseModel):
    session_id: str
    piece_id: str
    section_id: str
    stage: str


@router.post("/skip_stage")
async def skip_stage(body: SkipBody, user_id: str = Depends(current_user)):
    """"I already know this" — clear a whole stage without inflating mastery.

    Without it, a player who can already read the piece has to tap through
    every two-bar chunk before the app lets them do anything useful.
    """
    own_piece(user_id, body.piece_id)
    own_session(user_id, body.session_id, body.piece_id)
    world = load(user_id, body.piece_id)
    _section(world, body.section_id)
    steps = world["ladders"].get(body.section_id, [])
    nailed = {a["step_key"] for a in world["attempts"] if a.get("self_report") == "nailed"}

    rows = [{
        "id": str(uuid.uuid4()),
        "session_id": body.session_id,
        "user_id": user_id,
        "section_id": body.section_id,
        "step_key": step["key"],
        "stage": step["stage"],
        "self_report": "nailed",
        "skipped": True,
    } for step in steps if step["stage"] == body.stage and step["key"] not in nailed]

    if rows:
        _record(world, user_id, body.section_id, rows)
    return state(world, body.session_id)


class StruggleBody(BaseModel):
    session_id: str
    piece_id: str
    section_id: str
    step_key: str
    stage: str


@router.post("/struggling")
async def struggling(body: StruggleBody, user_id: str = Depends(current_user)):
    """Break the current step down.

    First tap narrows deterministically — instant and free. Only a second tap
    on the same step pays for a diagnosis.
    """
    own_piece(user_id, body.piece_id)
    own_session(user_id, body.session_id, body.piece_id)
    client = db()
    world = load(user_id, body.piece_id)
    section = _section(world, body.section_id)

    steps = world["ladders"].get(body.section_id, []) + world["remediation"]
    step = next((s for s in steps if s["key"] == body.step_key), None)
    if not step:
        return {"error": "step not found"}

    prior = [a for a in world["attempts"]
             if a["step_key"] == body.step_key and a.get("self_report") == "struggling"]

    client.table("step_attempts").insert({
        "id": str(uuid.uuid4()),
        "session_id": body.session_id,
        "user_id": user_id,
        "section_id": body.section_id,
        "step_key": body.step_key,
        "stage": body.stage,
        "self_report": "struggling",
    }).execute()

    if prior:
        profile = (
            client.table("profiles").select("piano_level, years_experience")
            .eq("id", user_id).maybe_single().execute()
        )
        drills = remediate.diagnose(
            step, section,
            [a for a in world["attempts"] if a["step_key"] == body.step_key],
            (profile.data if profile else None) or {},
        )
    else:
        drills = remediate.narrow(step, section)

    plan = (
        client.table("practice_plans").select("id")
        .eq("piece_id", body.piece_id).limit(1).execute()
    ).data
    if not plan:
        return {"error": "no plan for this piece"}

    highest = (
        client.table("plan_steps").select("order_index")
        .eq("plan_id", plan[0]["id"]).order("order_index", desc=True)
        .limit(1).execute()
    ).data
    order = (highest[0]["order_index"] + 1) if highest else 0

    # Appended, not spliced in: the scheduler surfaces remediation by priority,
    # so nothing downstream has to be renumbered.
    rows = [{
        "id": str(uuid.uuid4()),
        "plan_id": plan[0]["id"],
        "section_id": body.section_id,
        "order_index": order + i,
        "title": d["title"],
        "description": d["description"],
        "target_tempo": d["target_tempo"] or 0,
        "drill_type": "loop",
        "is_checkpoint": False,
        "unlock_requirement": 0,
        "focus_start_measure": d["focus_start_measure"],
        "focus_end_measure": d["focus_end_measure"],
        "success_criterion": "",
        "source": "remediation",
        "stage": d["stage"],
        "metronome": d["metronome"],
    } for i, d in enumerate(drills)]
    client.table("plan_steps").insert(rows).execute()

    return state(load(user_id, body.piece_id), body.session_id)


class EndBody(BaseModel):
    session_id: str
    total_seconds: int = Field(0, ge=0, le=MAX_SESSION_SECONDS)


@router.post("/session/end")
async def end(body: EndBody, user_id: str = Depends(current_user)):
    own_session(user_id, body.session_id)
    # First end wins: a retried or duplicate close must not move ended_at.
    db().table("practice_sessions").update({
        "ended_at": _now().isoformat(),
        "total_seconds": body.total_seconds,
    }).eq("id", body.session_id).is_("ended_at", "null").execute()
    return {"status": "ended"}
