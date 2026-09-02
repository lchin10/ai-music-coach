import json
import os
from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, Form
from app import schema
from app.service.sheet_music_detector import (
    SheetMusicDetector,
    get_sheet_music_detector,
)
from app.service.sheet_music_processor import (
    SheetMusicProcessor,
    get_sheet_music_processor,
)

router = APIRouter(prefix="/sheet_music", tags=["sheet_music"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.get("/schema")
async def check_schema(
    service: SheetMusicProcessor = Depends(get_sheet_music_processor),
):
    """Report any expected table/column the database is missing.

    `{"up_to_date": true}` means every migration has been applied.
    """
    if not service.supabase:
        return {"up_to_date": False, "error": "supabase client not initialised"}

    missing = schema.check(service.supabase)
    return {
        "up_to_date": not missing,
        "missing": missing,
        "hint": None if not missing else "run the SQL in backend/migrations/ in order",
    }


@router.post("/detector")
async def check_sheet_music(
    pdf_file: UploadFile = File(...),
    service: SheetMusicDetector = Depends(get_sheet_music_detector),
):
    file_bytes = await pdf_file.read()

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return {
            "sheet_music": False,
            "reason": "too_large",
            "bytes": len(file_bytes),
            "max_bytes": MAX_UPLOAD_BYTES,
        }

    result = service.detect(file_bytes)
    print(result)
    return result


@router.post("/process")
async def process_sheet_music(
    background_tasks: BackgroundTasks,
    pdf_file: UploadFile = File(...),
    piece_id: str = Form(...),
    user_id: str = Form(None),
    service: SheetMusicProcessor = Depends(get_sheet_music_processor),
):
    """Start background processing: PDF -> MusicXML -> parse -> generate plans"""
    file_bytes = await pdf_file.read()
    # schedule background task and return immediately
    background_tasks.add_task(
        service.process, file_bytes, piece_id, user_id, pdf_file.filename
    )
    return {"status": "processing_started"}


@router.post("/retry")
async def retry_piece(
    background_tasks: BackgroundTasks,
    piece_id: str = Form(...),
    service: SheetMusicProcessor = Depends(get_sheet_music_processor),
):
    """Re-run processing for a piece already in the database.

    Pulls the original PDF back out of storage, so the user doesn't re-upload.
    Runs from scratch — there is no resume, which is exactly why checkpointing
    was dropped: a clean re-run is a few minutes and one fan-out.
    """
    if not service.supabase:
        return {"error": "storage unavailable"}

    row = (
        service.supabase.table("pieces")
        .select("id, user_id, title, file_path")
        .eq("id", piece_id)
        .single()
        .execute()
    ).data
    if not row or not row.get("file_path"):
        return {"error": "piece not found"}

    # Reprocessing recreates sections with fresh UUIDs, and every mastery row
    # and ladder key hangs off section_id (see migrations 001 and 007). Once
    # there is real practice history, silently orphaning it is worse than
    # leaving a mediocre plan in place.
    sections = (
        service.supabase.table("sections").select("id").eq("piece_id", piece_id).execute()
    ).data or []
    if sections:
        practised = (
            service.supabase.table("step_attempts")
            .select("id", count="exact")
            .in_("section_id", [s["id"] for s in sections])
            .limit(1)
            .execute()
        )
        if practised.count:
            return {
                "error": "This piece has practice progress — "
                         "retrying would reset it."
            }

    pdf_bytes = service.supabase.storage.from_("pieces").download(row["file_path"])

    service.supabase.table("pieces").update(
        {"status": "processing", "processing_stage": "queued", "failure_reason": None}
    ).eq("id", piece_id).execute()

    background_tasks.add_task(
        service.process, pdf_bytes, piece_id, row.get("user_id"), row["title"]
    )
    return {"status": "processing_started"}


@router.post("/create_section")
async def create_test_section(
    piece_id: Annotated[
        str,
        Form(..., examples=["597a0f78-d4ba-40cd-bcb5-ac4995a53450"]),
    ],
    service: SheetMusicProcessor = Depends(get_sheet_music_processor),
):
    """Test endpoint: insert a fluff section + practice plan + steps for a given piece_id."""
    section_id = str(uuid.uuid4())
    plan_id = str(uuid.uuid4())

    section = {
        "id": section_id,
        "piece_id": piece_id,
        "title": "Test Section",
        "start_measure": 1,
        "end_measure": 8,
        "difficulty": 42,
        "notes": "This is a test section created by the /create_section endpoint.",
        "analysis_data": {
            "key_challenges": ["test challenge"],
            "techniques": ["test technique"],
            "musical_character": "test",
        },
    }

    plan = {"id": plan_id, "piece_id": piece_id, "version": 1}

    steps = [
        {
            "id": str(uuid.uuid4()),
            "plan_id": plan_id,
            "section_id": section_id,
            "order_index": 0,
            "title": "Hands separate mm. 1–8",
            "description": "Practice each hand alone through measures 1–8 at 60 bpm.",
            "target_tempo": 60,
            "drill_type": "hands_separate",
            "is_checkpoint": False,
            "unlock_requirement": 0,
        },
        {
            "id": str(uuid.uuid4()),
            "plan_id": plan_id,
            "section_id": section_id,
            "order_index": 1,
            "title": "Checkpoint mm. 1–8",
            "description": "Play through hands together at performance tempo.",
            "target_tempo": 80,
            "drill_type": "checkpoint",
            "is_checkpoint": True,
            "unlock_requirement": 60,
        },
    ]

    service.supabase.table("sections").insert(section).execute()
    service.supabase.table("practice_plans").insert(plan).execute()
    service.supabase.table("plan_steps").insert(steps).execute()

    return {"section_id": section_id, "plan_id": plan_id, "steps": len(steps)}
