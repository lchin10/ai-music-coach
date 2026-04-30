import json
import base64
import numpy as np
import cv2
import fitz  # PyMuPDF
from PIL import Image
import io

class OcrService:

  def has_staff_lines(self, image_bytes):
    image = Image.open(io.BytesIO(image_bytes))  # ✅ convert bytes → image
    image = image.convert("RGB")
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_BGR2GRAY)

    # detect horizontal lines
    edges = cv2.Canny(gray, 50, 150)

    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=200,
        minLineLength=100,
        maxLineGap=10
    )

    if lines is None:
      return False

    horizontal_lines = 0

    for line in lines:
      x1, y1, x2, y2 = line[0]
      if abs(y1 - y2) < 3:  # almost horizontal
        horizontal_lines += 1

    # sheet music usually has MANY horizontal lines
    return horizontal_lines > 20

  def pdf_to_images(self, pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []

    for page in doc:
      pix = page.get_pixmap()
      img = pix.pil_tobytes(format="PNG")
      images.append(img)

    return images

  def sheet_music(self, pdf_bytes):
    images = self.pdf_to_images(pdf_bytes)

    for img in images:
      if self.has_staff_lines(img):
        return {
            "statusCode": 200,
            "body": json.dumps({"sheet_music": True})
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"sheet_music": False})
    }


def get_ocr_service() -> OcrService:
  return OcrService()
