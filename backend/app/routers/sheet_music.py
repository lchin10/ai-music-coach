from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks, Form
from app import schema
from app.auth import current_user, own_piece
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
    _user: str = Depends(current_user),
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
    _user: str = Depends(current_user),
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
    service: SheetMusicProcessor = Depends(get_sheet_music_processor),
    user_id: str = Depends(current_user),
):
    """Start background processing: PDF -> MusicXML -> parse -> generate plans"""
    own_piece(user_id, piece_id)
    file_bytes = await pdf_file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
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
    user_id: str = Depends(current_user),
):
    """Re-run processing for a piece already in the database.

    Pulls the original PDF back out of storage, so the user doesn't re-upload.
    Runs from scratch — there is no resume, which is exactly why checkpointing
    was dropped: a clean re-run is a few minutes and one fan-out.
    """
    own_piece(user_id, piece_id)
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
