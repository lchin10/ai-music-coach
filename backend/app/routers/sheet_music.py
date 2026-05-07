import json
import os
from fastapi import APIRouter, Depends, UploadFile, File
from app.service.sheet_music_detector import SheetMusicDetector, get_sheet_music_detector

router = APIRouter(prefix="/sheet_music", tags=["sheet_music"])

@router.post("/detector")
async def check_sheet_music(
  pdf_file: UploadFile = File(...),
  service: SheetMusicDetector = Depends(get_sheet_music_detector)
):
  file_bytes = await pdf_file.read()
  result = service.detect(file_bytes)
  print(result)
  return result
