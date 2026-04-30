import json
import os
from fastapi import APIRouter, Depends, UploadFile, File
from app.service.ocr_check import OcrService, get_ocr_service

router = APIRouter(prefix="/ocr_check", tags=["ocr_check"])

@router.post("/")
async def check_sheet_music(
  pdf_file: UploadFile = File(...),
  service: OcrService = Depends(get_ocr_service)
):
  file_bytes = await pdf_file.read()
  result = service.sheet_music(file_bytes)
  print(result)
  return result
