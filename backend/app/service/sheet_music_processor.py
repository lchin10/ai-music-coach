import os
import uuid
import shutil
import tempfile
import subprocess
from typing import Optional

import anthropic
from music21 import converter

from supabase import create_client


PRACTICE_PLAN_TOOL = {
    "name": "create_practice_plan",
    "description": "Create a structured practice plan for a piece of sheet music.",
    "input_schema": {
        "type": "object",
        "required": ["sections"],
        "properties": {
            "sections": {
                "type": "array",
                "description": "3 to 5 sections dividing the piece into manageable chunks",
                "items": {
                    "type": "object",
                    "required": ["title", "start_measure", "end_measure", "difficulty", "notes", "analysis_data", "steps"],
                    "properties": {
                        "title": {"type": "string", "description": "Short descriptive name, e.g. 'Opening Theme'"},
                        "start_measure": {"type": "integer"},
                        "end_measure": {"type": "integer"},
                        "difficulty": {"type": "integer", "description": "0 (very easy) to 100 (extremely hard)"},
                        "notes": {"type": "string", "description": "Musical observations about this section"},
                        "analysis_data": {
                            "type": "object",
                            "properties": {
                                "key_challenges": {"type": "array", "items": {"type": "string"}},
                                "techniques": {"type": "array", "items": {"type": "string"}},
                                "musical_character": {"type": "string"}
                            }
                        },
                        "steps": {
                            "type": "array",
                            "description": "Ordered practice steps for this section (2-4 per section)",
                            "items": {
                                "type": "object",
                                "required": ["title", "description", "target_tempo", "drill_type", "is_checkpoint", "unlock_requirement"],
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string", "description": "Specific instruction, e.g. 'Practice RH alone measures 12-20 at 60 bpm, focus on the leap from C4 to G5'"},
                                    "target_tempo": {"type": "integer", "description": "Target BPM for this drill"},
                                    "drill_type": {
                                        "type": "string",
                                        "enum": ["hands_separate", "hands_together", "loop", "slow_practice", "tempo_building", "rhythm_variation", "metronome", "articulation_focus", "checkpoint"]
                                    },
                                    "is_checkpoint": {"type": "boolean"},
                                    "unlock_requirement": {"type": "integer", "description": "Mastery 0-100 required to unlock; 0 = always available"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

_SYSTEM_PROMPT = """You are an expert piano teacher creating detailed practice plans for students.

Given a musical analysis of a piece, create a comprehensive practice plan that:
1. Divides the piece into 3-5 logical sections based on musical structure (not just equal measure splits)
2. For each section, provides 2-4 specific practice steps ordered beginner → advanced
3. Each step has very specific instructions referencing actual musical elements (exact measure numbers, BPM, technique)
4. Uses appropriate drill types and tempos based on the piece's actual tempo and difficulty
5. Includes checkpoint steps to consolidate learning

For piano pieces, the typical progression per section is:
- Hands separate (slow)
- Hands together (slow)
- Tempo building
- Checkpoint at or near performance tempo

Be musical and specific — reference key signature, time signature, tempo markings, and the challenges you'd expect given the measure ranges and note density."""


class SheetMusicProcessor:
    def __init__(self):
        supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        print("SUPABASE KEY PREFIX:", supabase_key[:20])
        print("Using service role:", bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")))
        self.supabase = create_client(supabase_url, supabase_key) if (supabase_url and supabase_key) else None

        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.ai = anthropic.Anthropic(api_key=api_key) if api_key else None

    def _run_audiveris(self, pdf_path: str, outdir: str) -> Optional[str]:
        _default_win = r"C:\Program Files\Audiveris\Audiveris.exe"
        audiveris = (
            os.getenv("AUDIVERIS_PATH")
            or shutil.which("audiveris")
            or (_default_win if os.path.exists(_default_win) else None)
        )
        if not audiveris:
            print("[processor] ERROR: audiveris not found on PATH and not at default Windows location")
            return None
        print(f"[processor] Running audiveris: {audiveris}")
        cmd = [audiveris, "-batch", "-export", "-output", outdir, pdf_path]
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[processor] audiveris stdout: {result.stdout.decode()[:500]}")
        except Exception as e:
            print(f"[processor] ERROR running audiveris: {e}")
            return None
        for root, _, files in os.walk(outdir):
            for f in files:
                if f.lower().endswith((".musicxml", ".xml", ".mxl")):
                    found = os.path.join(root, f)
                    print(f"[processor] MusicXML found: {found}")
                    return found
        print(f"[processor] ERROR: no MusicXML output found in {outdir}")
        return None

    def _extract_music_context(self, score) -> dict:
        context = {}

        if score.metadata and score.metadata.title:
            context["title"] = score.metadata.title

        keys = list(score.flatten().getElementsByClass("KeySignature"))
        if keys:
            context["key"] = str(keys[0].asKey())

        times = list(score.flatten().getElementsByClass("TimeSignature"))
        if times:
            context["time_signature"] = times[0].ratioString

        tempos = list(score.flatten().getElementsByClass("MetronomeMark"))
        if tempos:
            mm = tempos[0]
            if mm.number:
                context["tempo_bpm"] = int(mm.number)
            if mm.text:
                context["tempo_text"] = mm.text

        parts = list(score.parts)
        context["parts"] = [p.partName or f"Part {i + 1}" for i, p in enumerate(parts)]

        if parts:
            first_part = parts[0]
            measures = list(first_part.getElementsByClass("Measure"))
            context["total_measures"] = len(measures)

            note_density = [
                len(list(m.recurse().getElementsByClass("Note")))
                for m in measures
            ]
            if note_density:
                avg = sum(note_density) / len(note_density)
                context["avg_notes_per_measure"] = round(avg, 1)
                context["max_notes_per_measure"] = max(note_density)
                # Cap at 15 to keep the prompt concise
                context["dense_measures"] = [
                    i + 1 for i, n in enumerate(note_density) if n > avg * 1.5
                ][:15]

        return context

    def _generate_plan_with_ai(self, context: dict) -> Optional[dict]:
        if not self.ai:
            return None

        lines = []
        if "title" in context:
            lines.append(f"Title: {context['title']}")
        if "key" in context:
            lines.append(f"Key: {context['key']}")
        if "time_signature" in context:
            lines.append(f"Time signature: {context['time_signature']}")
        if "tempo_bpm" in context:
            tempo = f"{context['tempo_bpm']} BPM"
            if "tempo_text" in context:
                tempo = f"{context['tempo_text']} ({tempo})"
            lines.append(f"Tempo: {tempo}")
        if "total_measures" in context:
            lines.append(f"Total measures: {context['total_measures']}")
        if "parts" in context:
            lines.append(f"Parts: {', '.join(context['parts'])}")
        if "avg_notes_per_measure" in context:
            lines.append(f"Average notes/measure: {context['avg_notes_per_measure']}")
        if context.get("dense_measures"):
            lines.append(f"High-density measures (likely difficult): {context['dense_measures']}")

        try:
            response = self.ai.messages.create(
                model="claude-opus-4-8",
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=[PRACTICE_PLAN_TOOL],
                tool_choice={"type": "tool", "name": "create_practice_plan"},
                messages=[
                    {
                        "role": "user",
                        "content": f"Create a detailed practice plan for this piece:\n\n{chr(10).join(lines)}",
                    }
                ],
            )
        except Exception as e:
            print(f"[processor] AI generation failed, using fallback: {e}")
            return None

        for block in response.content:
            if block.type == "tool_use" and block.name == "create_practice_plan":
                return block.input

        return None

    def _fallback_plan(self, score) -> dict:
        parts = list(score.parts)
        first_part = parts[0] if parts else None
        total = len(list(first_part.getElementsByClass("Measure"))) if first_part else 30
        n = 3 if total < 40 else (4 if total < 80 else 5)

        sections = []
        for i in range(n):
            start = int(i * total / n) + 1
            end = int((i + 1) * total / n)

            difficulty = 20
            if first_part:
                notes, counted = 0, 0
                for m in first_part.measures(start, end):
                    counted += 1
                    notes += len(list(m.recurse().getElementsByClass("Note")))
                avg = notes / counted if counted else 0
                difficulty = 20 if avg < 5 else 40 if avg < 10 else 60 if avg < 20 else 80 if avg < 30 else 100

            sections.append({
                "title": f"Section {i + 1} (mm. {start}–{end})",
                "start_measure": start,
                "end_measure": end,
                "difficulty": difficulty,
                "notes": "",
                "analysis_data": {},
                "steps": [
                    {
                        "title": f"Hands separate, mm. {start}–{end}",
                        "description": f"Practice each hand alone through measures {start}–{end} at a slow, comfortable tempo.",
                        "target_tempo": 60,
                        "drill_type": "hands_separate",
                        "is_checkpoint": False,
                        "unlock_requirement": 0,
                    },
                    {
                        "title": f"Hands together, mm. {start}–{end}",
                        "description": f"Combine both hands through measures {start}–{end}, prioritising accuracy over speed.",
                        "target_tempo": 60,
                        "drill_type": "hands_together",
                        "is_checkpoint": False,
                        "unlock_requirement": 50,
                    },
                ],
            })
        return {"sections": sections}

    def process(self, pdf_bytes: bytes, piece_id: str, _user_id: Optional[str], file_name: str):
        print(f"[processor] Starting processing for piece_id={piece_id}, file={file_name}")
        tmpdir = tempfile.mkdtemp(prefix="smp_")
        try:
            pdf_path = os.path.join(tmpdir, file_name)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            outdir = os.path.join(tmpdir, "out")
            os.makedirs(outdir, exist_ok=True)

            musicxml_path = self._run_audiveris(pdf_path, outdir)
            if not musicxml_path:
                if self.supabase and piece_id:
                    self.supabase.table("pieces").update({"status": "failed", "failure_reason": "Conversion to MusicXML failed"}).eq("id", piece_id).execute()
                return

            print("[processor] Parsing MusicXML with music21...")
            score = converter.parse(musicxml_path)
            if not list(score.parts):
                if self.supabase and piece_id:
                    self.supabase.table("pieces").update({"status": "failed", "failure_reason": "No parts found in MusicXML"}).eq("id", piece_id).execute()
                return

            context = self._extract_music_context(score)
            print(f"[processor] Music context: {context}")

            print("[processor] Generating practice plan...")
            plan = self._generate_plan_with_ai(context) or self._fallback_plan(score)
            print(f"[processor] Plan has {len(plan['sections'])} sections")

            plan_id = str(uuid.uuid4())
            sections_db = []
            plan_steps_db = []
            global_order = 0

            for sec in plan["sections"]:
                section_id = str(uuid.uuid4())
                sections_db.append({
                    "id": section_id,
                    "piece_id": piece_id,
                    "title": sec["title"],
                    "start_measure": sec["start_measure"],
                    "end_measure": sec["end_measure"],
                    "difficulty": sec["difficulty"],
                    "notes": sec.get("notes", ""),
                    "analysis_data": sec.get("analysis_data", {}),
                })
                for step in sec.get("steps", []):
                    plan_steps_db.append({
                        "id": str(uuid.uuid4()),
                        "plan_id": plan_id,
                        "section_id": section_id,
                        "order_index": global_order,
                        "title": step["title"],
                        "description": step["description"],
                        "target_tempo": step["target_tempo"],
                        "drill_type": step["drill_type"],
                        "is_checkpoint": step.get("is_checkpoint", False),
                        "unlock_requirement": step.get("unlock_requirement", 0),
                    })
                    global_order += 1

            if self.supabase:
                print(f"[processor] Inserting {len(sections_db)} sections, {len(plan_steps_db)} steps...")
                self.supabase.table("sections").insert(sections_db).execute()
                self.supabase.table("practice_plans").insert({"id": plan_id, "piece_id": piece_id, "version": 1}).execute()
                self.supabase.table("plan_steps").insert(plan_steps_db).execute()
                self.supabase.table("pieces").update({"status": "ready"}).eq("id", piece_id).execute()
                print("[processor] Done — piece marked ready")
            else:
                print("[processor] ERROR: supabase client not initialised — check NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.local")

        except Exception as e:
            print(f"[processor] EXCEPTION: {e}")
            import traceback; traceback.print_exc()
            if self.supabase and piece_id:
                self.supabase.table("pieces").update({"status": "failed", "failure_reason": str(e)}).eq("id", piece_id).execute()
        finally:
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass


def get_sheet_music_processor() -> SheetMusicProcessor:
    return SheetMusicProcessor()
