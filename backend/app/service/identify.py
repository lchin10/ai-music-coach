"""Work out what the piece actually is.

Audiveris OCRs the title block, and on a scan it does so badly:

    title        None
    movementName 'J = is - as'                    (the tempo marking)
    composer     'S. RACHMANINOFF, 0p. 3. Na. 2'  (Op -> 0p, No -> Na)

The upload filename usually carries the rest ("IMSLP11125-Godowsky_APS_47_
Rachmaninoff-Prelude_Op.3_No.2.pdf"). Between the two there is always enough
to name the piece, and never enough for a regex to do it — the OCR errors are
different every time. So this is one small model call: a few hundred tokens
next to a fan-out that costs thousands, and it runs once per upload.

Non-fatal by design. A piece with a filename for a title is still a usable
piece; losing the whole upload over a cosmetic field would not be.
"""

import json
import os
import re

MODEL = "claude-opus-5"

SYSTEM = """You identify printed sheet music from noisy OCR and a filename.

The OCR comes from optical music recognition on a scan, so the title block is often mangled: "Op." reads as "0p.", "No." as "Na.", and the tempo marking is frequently mistaken for the title. The filename is usually cleaner but full of catalogue junk (IMSLP ids, underscores, plate numbers).

Return the piece as a musician would write it on a programme.

- work_title: the work, with key and catalogue number when you are confident of them — "Prelude in C-sharp minor, Op. 3 No. 2". No composer name in it.
- composer: the composer's usual full name — "Sergei Rachmaninoff". If the score is an arrangement or transcription, append it: "Sergei Rachmaninoff (arr. Leopold Godowsky)".
- Correct obvious OCR damage, but do NOT invent details you cannot see. If you cannot tell the key or opus, leave them out rather than guessing.
- If the evidence names no recognisable work, put a tidied version of the filename in work_title and leave composer empty."""

TOOL = {
    "name": "identify_piece",
    "description": "Name the work and its composer.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["work_title", "composer"],
        "properties": {
            "work_title": {"type": "string"},
            "composer": {"type": "string", "description": "May be empty if unknown."},
        },
    },
}


def tidy_filename(file_name: str) -> str:
    """The fallback title: readable, and never worse than what we show today."""
    name = os.path.splitext(file_name or "")[0]
    name = re.sub(r"^IMSLP\d+[-_]*", "", name, flags=re.I)
    name = re.sub(r"[_-]+", " ", name)
    return re.sub(r"\s+", " ", name).strip() or (file_name or "Untitled")


def identify(features: dict, file_name: str, extra: dict = None) -> dict:
    """{"work_title", "composer"} — always returns something usable."""
    fallback = {"work_title": tidy_filename(file_name), "composer": ""}

    score = features.get("score", {}) if features else {}
    evidence = {
        "filename": file_name,
        "ocr_title": score.get("title"),
        "ocr_composer": score.get("composer"),
        "parts": score.get("parts"),
        "keys": score.get("keys", [])[:2],
        "time_signatures": score.get("time_signatures", [])[:2],
        "tempos": score.get("tempos", [])[:2],
        **(extra or {}),
    }

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM,
            output_config={"effort": "low"},
            tools=[TOOL],
            tool_choice={"type": "tool", "name": TOOL["name"]},
            messages=[{
                "role": "user",
                "content": "Identify this score.\n\n"
                           + json.dumps(evidence, indent=1, default=str),
            }],
        )
        for block in response.content:
            if block.type == "tool_use":
                title = (block.input.get("work_title") or "").strip()
                composer = (block.input.get("composer") or "").strip()
                if title:
                    print(f"[identify] {title} — {composer or 'composer unknown'}")
                    return {"work_title": title, "composer": composer}
    except Exception as e:
        print(f"[identify] could not identify the piece ({e}); using the filename")

    return fallback
