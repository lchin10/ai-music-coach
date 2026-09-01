import json
import cv2
import numpy as np
from PIL import Image
import io
import fitz  # PyMuPDF

# A piano piece is typically 2-12 pages; a fake book or anthology is 50-200.
# Rejecting here costs nothing — this runs before Audiveris and before any
# LLM call — and it is what stops someone uploading a whole songbook.
MAX_PAGES = 20


class SheetMusicDetector:
  def __init__(self):
    # Blob detector setup (for note heads)
    params = cv2.SimpleBlobDetector_Params()
    params.filterByArea = True
    params.minArea = 20
    params.maxArea = 500

    params.filterByCircularity = True
    params.minCircularity = 0.5

    self.blob_detector = cv2.SimpleBlobDetector_create(params)

  # ---------------------------
  # PDF → images
  # ---------------------------
  def page_image(self, page):
    return page.get_pixmap().pil_tobytes(format="PNG")

  # ---------------------------
  # Preprocessing
  # ---------------------------
  def preprocess(self, image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 150, 255, cv2.THRESH_BINARY_INV)

    return gray, thresh

  # ---------------------------
  # Detect horizontal staff lines
  # ---------------------------
  def detect_staff_lines(self, gray):
    edges = cv2.Canny(gray, 50, 150)

    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=150,
        minLineLength=100,
        maxLineGap=10
    )

    if lines is None:
      return []

    horizontals = []
    for line in lines:
      x1, y1, x2, y2 = line[0]
      if abs(y1 - y2) < 3:
        horizontals.append((x1, y1, x2, y2))

    return horizontals

  # ---------------------------
  # Group lines into staffs (5 lines)
  # ---------------------------
  def group_staffs(self, lines):
    if not lines:
      return 0

    ys = sorted([(y1 + y2) / 2 for x1, y1, x2, y2 in lines])

    clusters = []
    current = [ys[0]]

    for y in ys[1:]:
      if abs(y - current[-1]) < 10:
        current.append(y)
      else:
        clusters.append(current)
        current = [y]
    clusters.append(current)

    staff_groups = 0

    for cluster in clusters:
      if 4 <= len(cluster) <= 6:
        diffs = np.diff(cluster)
        if len(diffs) > 0 and np.std(diffs) < 2:
          staff_groups += 1

    return staff_groups

  # ---------------------------
  # Detect vertical bar lines
  # ---------------------------
  def detect_vertical_lines(self, gray):
    edges = cv2.Canny(gray, 50, 150)

    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=100,
        minLineLength=50,
        maxLineGap=5
    )

    if lines is None:
      return 0

    count = 0
    for line in lines:
      x1, y1, x2, y2 = line[0]
      if abs(x1 - x2) < 3:
        count += 1

    return count

  # ---------------------------
  # Detect note heads (blobs)
  # ---------------------------
  def detect_note_blobs(self, gray):
    keypoints = self.blob_detector.detect(gray)
    return len(keypoints)

  # ---------------------------
  # Score a single page
  # ---------------------------
  def score_page(self, image_bytes):
    gray, thresh = self.preprocess(image_bytes)

    staff_lines = self.detect_staff_lines(gray)
    staff_groups = self.group_staffs(staff_lines)

    vertical_lines = self.detect_vertical_lines(gray)
    note_blobs = self.detect_note_blobs(gray)

    score = 0

    # Staff structure is strongest signal
    if staff_groups >= 2:
      score += 2

    # Notes
    if note_blobs > 25:
      score += 2

    # Bar lines
    if vertical_lines > 5:
      score += 1

    return {
        "score": score,
        "staff_groups": staff_groups,
        "note_blobs": note_blobs,
        "vertical_lines": vertical_lines
    }

  # ---------------------------
  # Main API
  # ---------------------------
  def detect(self, pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if doc.page_count > MAX_PAGES:
      return {
          "sheet_music": False,
          "reason": "too_many_pages",
          "pages": doc.page_count,
          "max_pages": MAX_PAGES,
      }

    # Render pages one at a time and stop at the first hit — page 1 is
    # usually enough, so there is no reason to rasterise the whole document.
    for page in doc:
      result = self.score_page(self.page_image(page))

      if result["score"] >= 3:
        return {
            "sheet_music": True,
            "details": result
        }

    return {
        "sheet_music": False,
        "reason": "no_notation",
    }


def get_sheet_music_detector() -> SheetMusicDetector:
  return SheetMusicDetector()
