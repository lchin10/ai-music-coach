"""Crop the source PDF to the staff systems covering a measure range.

The PDF is the ground truth — Audiveris drops fingerings, most dynamics and,
on dense scores, notes — so what the user sees is the real engraving.

Systems are found by whitespace gaps rather than staff lines. Staff-line
detection needs to know how many staves make a system, and that is not fixed:
the Godowsky Rachmaninoff switches from a 2-stave to a 6-stave layout partway
through, where line detection missed 3 of 8 staves. Whitespace works for both.

Gap size alone can't classify a break (one score's inter-system gap is another
page's intra-system gap), so the number of systems per page comes from the
MusicXML, which records system and page breaks reliably even where note
recognition struggles.
"""

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 is a hard dep of the detector
    cv2 = None

import fitz  # PyMuPDF

DPI = 150
INK_FRACTION = 0.004   # a row this inky counts as content
MIN_BAND_HEIGHT = 40   # ignore specks and rules
# Tempo marks and fingerings sit above a system, pedal marks below; both get
# clipped at a tighter margin. Half a band gap is roughly the free space.
MARGIN = 32


def page_gray(document, index: int):
    pix = document[index].get_pixmap(dpi=DPI)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img[:, :, 0]


def ink_bands(gray) -> list:
    """Contiguous runs of inked rows, top to bottom."""
    height, width = gray.shape
    inked = (gray < 160).sum(axis=1) > max(2, width * INK_FRACTION)

    bands, start = [], None
    for y, on in enumerate(inked):
        if on and start is None:
            start = y
        elif not on and start is not None:
            if y - start >= MIN_BAND_HEIGHT:
                bands.append((start, y))
            start = None
    if start is not None and height - start >= MIN_BAND_HEIGHT:
        bands.append((start, height))
    return bands


def system_bands(gray, expected: int) -> list:
    """Split one page into `expected` systems, or [] if that isn't possible.

    Titles, footers and page numbers form their own short bands and are
    dropped by height before merging.
    """
    bands = ink_bands(gray)
    if not bands or expected < 1:
        return []

    heights = [b - a for a, b in bands]
    cutoff = np.median(heights) * 0.45
    music = [b for b in bands if (b[1] - b[0]) > cutoff]

    if len(music) < expected:
        # Fewer bands than systems — some systems ran together. Cropping would
        # cut through music, so let the caller fall back to the whole page.
        return []

    # Repeatedly close the smallest gap until the band count matches. A
    # multi-stave system arrives as several bands separated by tiny gaps,
    # so the smallest gaps are always the intra-system ones.
    bands = [list(b) for b in music]
    while len(bands) > expected:
        gaps = [(bands[i + 1][0] - bands[i][1], i) for i in range(len(bands) - 1)]
        _, i = min(gaps)
        bands[i][1] = bands[i + 1][1]
        del bands[i + 1]

    return [(a, b) for a, b in bands]


def crop_systems(pdf_bytes: bytes, layout: list) -> list:
    """Render each system named in `layout` to a PNG.

    layout: [{page, systems: [{index, start_measure, end_measure}]}]
    Returns [{page, start_measure, end_measure, png, cropped}] in reading order;
    `cropped` is False when the page had to be emitted whole.
    """
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = []

    for entry in layout:
        index = entry["page"]
        if index >= document.page_count:
            continue

        systems = entry["systems"]
        gray = page_gray(document, index)
        bands = system_bands(gray, len(systems)) if cv2 is not None else []
        height = gray.shape[0]

        if len(bands) != len(systems):
            # Whole page, labelled with everything on it — always correct,
            # just coarser than asked for.
            png = document[index].get_pixmap(dpi=DPI).tobytes("png")
            out.append({
                "page": index,
                "start_measure": systems[0]["start_measure"],
                "end_measure": systems[-1]["end_measure"],
                "png": png,
                "cropped": False,
            })
            continue

        pix = document[index].get_pixmap(dpi=DPI)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

        for system, (top, bottom) in zip(systems, bands):
            y0 = max(0, top - MARGIN)
            y1 = min(height, bottom + MARGIN)
            crop = img[y0:y1]
            ok, buffer = cv2.imencode(".png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
                                      if pix.n >= 3 else crop)
            if not ok:
                continue
            out.append({
                "page": index,
                "start_measure": system["start_measure"],
                "end_measure": system["end_measure"],
                "png": buffer.tobytes(),
                "cropped": True,
            })

    return out
