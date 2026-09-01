import os
import uuid
import shutil
import tempfile
import subprocess
from typing import Optional

from music21 import converter

from supabase import create_client

from app import schema
from app.graph import features as feat
from app.graph.build import build, postgres_checkpointer


class SheetMusicProcessor:
    def __init__(self):
        supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        print("SUPABASE KEY PREFIX:", supabase_key[:20])
        print("Using service role:", bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")))
        self.supabase = create_client(supabase_url, supabase_key) if (supabase_url and supabase_key) else None

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
            print(f"[processor] audiveris stdout (tail): {result.stdout.decode(errors='replace')[-1500:]}")
        except subprocess.CalledProcessError as e:
            # Surface what Audiveris actually said — the cause is usually in the
            # tail of stderr/stdout (e.g. a Java OutOfMemoryError or a step failure).
            out = (e.stdout or b"").decode(errors="replace")
            err = (e.stderr or b"").decode(errors="replace")
            print(
                f"[processor] ERROR: audiveris exited {e.returncode}\n"
                f"--- audiveris stdout (tail) ---\n{out[-2000:]}\n"
                f"--- audiveris stderr (tail) ---\n{err[-2000:]}"
            )
            return None
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

    # ----------------------------------------------------------------------
    # Supabase helpers
    # ----------------------------------------------------------------------

    def _stage(self, piece_id: str, stage: str):
        """Per-node progress the upload-confirmation page can show.

        Cosmetic — never let it fail the run. Without migration 001 the column
        doesn't exist, and a progress label is not worth losing a piece over.
        """
        if not (self.supabase and piece_id):
            return
        try:
            self.supabase.table("pieces").update({"processing_stage": stage}).eq("id", piece_id).execute()
        except Exception as e:
            print(f"[processor] could not set stage '{stage}' (run migration 001?): {e}")

    def _fail(self, piece_id: str, reason: str):
        print(f"[processor] FAILED: {reason}")
        if self.supabase and piece_id:
            self.supabase.table("pieces").update(
                {"status": "failed", "failure_reason": reason}
            ).eq("id", piece_id).execute()

    def _missing_migration(self) -> Optional[str]:
        """Check the schema before spending money, not after.

        _persist writes columns added by migration 001. Without it the whole
        fan-out runs, bills for N sections of Opus 5, and then throws on the
        insert — so probe first and fail for free.
        """
        if not self.supabase:
            return None
        missing = schema.check(self.supabase)
        if not missing:
            return None
        return "; ".join(f"{table}: {', '.join(cols)}" for table, cols in missing.items())

    def _store_musicxml(self, piece_id: str, user_id: Optional[str], path: str, features: dict):
        """Upload the score to the `pieces` bucket so the UI can render bars.

        Non-fatal: a piece with a plan but no notation is still useful, and
        losing the whole plan over a failed upload would not be.
        """
        if not (self.supabase and piece_id):
            return

        offset = features["score"].get("first_measure", 1)
        try:
            with open(path, "rb") as f:
                data = f.read()

            folder = user_id or "anonymous"
            key = f"{folder}/{piece_id}{os.path.splitext(path)[1] or '.mxl'}"
            self.supabase.storage.from_("pieces").upload(
                key,
                data,
                {"content-type": "application/vnd.recordare.musicxml", "upsert": "true"},
            )
            self.supabase.table("pieces").update(
                {"musicxml_path": key, "measure_offset": offset}
            ).eq("id", piece_id).execute()
            print(f"[processor] Stored MusicXML at {key} ({len(data)} bytes, offset {offset})")
        except Exception as e:
            print(f"[processor] could not store MusicXML (notation will be unavailable): {e}")
            # The offset is still worth recording even if the upload failed.
            try:
                self.supabase.table("pieces").update({"measure_offset": offset}).eq("id", piece_id).execute()
            except Exception:
                pass

    def _profile(self, user_id: Optional[str]) -> dict:
        """Collected at onboarding and, until now, never used by the planner."""
        if not (self.supabase and user_id):
            return {}
        try:
            response = (
                self.supabase.table("profiles")
                .select("piano_level, years_experience")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return response.data or {}
        except Exception as e:
            print(f"[processor] could not load profile: {e}")
            return {}

    # ----------------------------------------------------------------------
    # Fallback
    # ----------------------------------------------------------------------

    def _fallback_plan(self, score) -> dict:
        """Deterministic safety net. A mediocre plan beats status: failed."""
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
                # .measures() returns a Stream carrying the part's Instrument
                # alongside the measures; iterating it raw hands an Instrument
                # to .recurse() and throws.
                for m in first_part.measures(start, end).getElementsByClass("Measure"):
                    counted += 1
                    notes += len(list(m.recurse().getElementsByClass("Note")))
                avg = notes / counted if counted else 0
                difficulty = 20 if avg < 5 else 40 if avg < 10 else 60 if avg < 20 else 80 if avg < 30 else 100

            sections.append({
                "index": i,
                "title": f"Section {i + 1} (mm. {start}–{end})",
                "start_measure": start,
                "end_measure": end,
                "analysis": {"difficulty": difficulty},
                "steps": [
                    {
                        "title": f"Hands separate, mm. {start}–{end}",
                        "description": f"Practice each hand alone through measures {start}–{end} at a slow, comfortable tempo.",
                        "target_tempo": 60,
                        "drill_type": "hands_separate",
                        "focus_start_measure": start,
                        "focus_end_measure": end,
                        "success_criterion": "2 clean run-throughs per hand at 60 bpm",
                        "is_checkpoint": False,
                        "unlock_requirement": 0,
                    },
                    {
                        "title": f"Hands together, mm. {start}–{end}",
                        "description": f"Combine both hands through measures {start}–{end}, prioritising accuracy over speed.",
                        "target_tempo": 60,
                        "drill_type": "checkpoint",
                        "focus_start_measure": start,
                        "focus_end_measure": end,
                        "success_criterion": "2 clean run-throughs hands together at 60 bpm",
                        "is_checkpoint": True,
                        "unlock_requirement": 50,
                    },
                ],
            })

        counter = 0
        for section in sections:
            for step in section["steps"]:
                step["order_index"] = counter
                counter += 1

        return {"sections": sections, "structural_summary": ""}

    # ----------------------------------------------------------------------
    # Persistence
    # ----------------------------------------------------------------------

    def _persist(self, piece_id: str, plan: dict):
        """Sections belong to the PIECE, not the plan version.

        Plan revisions (Phase 3) rewrite plan_steps only. If sections were ever
        regenerated with fresh UUIDs, every future mastery and progress row
        keyed on section_id would orphan silently.
        """
        # PostgREST turns insert([]) into "?columns=()" and answers with an
        # opaque PGRST100 parse error, so never hand it an empty plan.
        if not plan.get("sections"):
            raise ValueError("refusing to persist a plan with no sections")

        plan_id = str(uuid.uuid4())
        sections_db, steps_db = [], []

        for section in plan["sections"]:
            section_id = str(uuid.uuid4())
            analysis = section.get("analysis", {})
            sections_db.append({
                "id": section_id,
                "piece_id": piece_id,
                "title": section["title"],
                "start_measure": section["start_measure"],
                "end_measure": section["end_measure"],
                "difficulty": analysis.get("difficulty", 50),
                "notes": analysis.get("musical_character", ""),
                "analysis_data": analysis,
            })
            for step in section["steps"]:
                steps_db.append({
                    "id": str(uuid.uuid4()),
                    "plan_id": plan_id,
                    "section_id": section_id,
                    "order_index": step["order_index"],
                    "title": step["title"],
                    "description": step["description"],
                    "target_tempo": step["target_tempo"],
                    "drill_type": step["drill_type"],
                    "focus_start_measure": step.get("focus_start_measure"),
                    "focus_end_measure": step.get("focus_end_measure"),
                    "success_criterion": step.get("success_criterion", ""),
                    "source": "plan",
                    "is_checkpoint": step.get("is_checkpoint", False),
                    "unlock_requirement": step.get("unlock_requirement", 0),
                })

        if not self.supabase:
            print("[processor] ERROR: supabase client not initialised — check NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env.local")
            return

        print(f"[processor] Inserting {len(sections_db)} sections, {len(steps_db)} steps...")
        self.supabase.table("sections").insert(sections_db).execute()
        self.supabase.table("practice_plans").insert({"id": plan_id, "piece_id": piece_id, "version": 1}).execute()
        self.supabase.table("plan_steps").insert(steps_db).execute()
        self.supabase.table("pieces").update({"status": "ready", "processing_stage": "done"}).eq("id", piece_id).execute()
        print("[processor] Done — piece marked ready")

    # ----------------------------------------------------------------------
    # Entry point
    # ----------------------------------------------------------------------

    def process(self, pdf_bytes: bytes, piece_id: str, user_id: Optional[str], file_name: str):
        print(f"[processor] Starting processing for piece_id={piece_id}, file={file_name}")
        missing = self._missing_migration()
        if missing:
            self._fail(
                piece_id,
                f"Backend database is out of date — run backend/migrations/001_planning_graph.sql. {missing}",
            )
            return

        tmpdir = tempfile.mkdtemp(prefix="smp_")
        score = None
        try:
            pdf_path = os.path.join(tmpdir, file_name)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            outdir = os.path.join(tmpdir, "out")
            os.makedirs(outdir, exist_ok=True)

            self._stage(piece_id, "converting")
            musicxml_path = self._run_audiveris(pdf_path, outdir)
            if not musicxml_path:
                self._fail(piece_id, "Conversion to MusicXML failed")
                return

            print("[processor] Parsing MusicXML with music21...")
            score = converter.parse(musicxml_path)
            if not list(score.parts):
                self._fail(piece_id, "No parts found in MusicXML")
                return

            self._stage(piece_id, "analyzing")
            try:
                features = feat.extract(score)
            except feat.TooLongError as e:
                # The guard that actually protects the bill: reject before the
                # fan-out, which is where the cost lives.
                self._fail(piece_id, f"Piece is too long to plan: {e}. Try uploading one movement.")
                return

            print(
                f"[processor] {features['score']['total_measures']} measures, "
                f"{len(features['score']['repeat_barlines'])} repeats, "
                f"{len(features['score']['double_barlines'])} double barlines"
            )

            # Keep the MusicXML — the frontend renders notation straight from
            # it. Without this the temp dir takes it and there is nothing to
            # draw the bars a drill refers to.
            self._store_musicxml(piece_id, user_id, musicxml_path, features)

            plan = self._run_graph(piece_id, user_id, features)
            if plan is None:
                print("[processor] graph failed — falling back to deterministic plan")
                plan = self._fallback_plan(score)

            print(f"[processor] Plan has {len(plan['sections'])} sections")
            self._persist(piece_id, plan)

        except Exception as e:
            print(f"[processor] EXCEPTION: {e}")
            import traceback; traceback.print_exc()
            if score is not None:
                try:
                    self._persist(piece_id, self._fallback_plan(score))
                    return
                except Exception as inner:
                    print(f"[processor] fallback also failed: {inner}")
            self._fail(piece_id, str(e))
        finally:
            try:
                shutil.rmtree(tmpdir)
            except Exception:
                pass

    def _run_graph(self, piece_id: str, user_id: Optional[str], features: dict) -> Optional[dict]:
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("[processor] ANTHROPIC_API_KEY unset — skipping graph")
            return None

        initial = {
            "piece_id": piece_id,
            "user_id": user_id,
            "profile": self._profile(user_id),
            "features": features,
            "revisions": 0,
        }
        config = {"configurable": {"thread_id": piece_id}, "recursion_limit": 50}

        try:
            saver = postgres_checkpointer()
            if saver is None:
                return self._as_plan(build().invoke(initial, config))

            with saver as checkpointer:
                checkpointer.setup()
                return self._as_plan(build(checkpointer).invoke(initial, config))
        except Exception as e:
            print(f"[processor] graph error: {e}")
            import traceback; traceback.print_exc()
            return None

    @staticmethod
    def _as_plan(state: dict) -> dict:
        return {
            "sections": state["sections"],
            "structural_summary": state.get("structural_summary", ""),
        }


def get_sheet_music_processor() -> SheetMusicProcessor:
    return SheetMusicProcessor()
