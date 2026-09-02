"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import useSession from "@/lib/userSession";
import ScorePages, { type PageImage } from "@/components/ScorePages";
import { Metronome } from "@/lib/metronome";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type Step = {
  key: string;
  section_id: string;
  stage: string;
  focus_start_measure: number;
  focus_end_measure: number;
  metronome: "off" | "optional" | "required";
  target_tempo: number | null;
  title: string;
  description: string;
  source: string;
};

type Action = {
  kind: string;
  section_id: string | null;
  section_title: string | null;
  step: Step | null;
  why: string;
};

type SectionRow = {
  id: string;
  title: string;
  start_measure: number;
  end_measure: number;
  mastery: number;
  reached_stage: string | null;
  complete: boolean;
  locked: boolean;
};

type StageRow = { stage: string; total: number; done: number; complete: boolean };

type State = {
  session_id: string | null;
  action: Action;
  sections: SectionRow[];
  stages: StageRow[];
};

const STAGE_LABEL: Record<string, string> = {
  notes: "Notes",
  thread: "Thread together",
  rhythm: "Rhythm",
  technique: "Technique",
  transition: "Transitions",
  pair: "Pair up",
  section: "Whole section",
  tempo: "Build tempo",
  integration: "Join sections",
};

const STAGE_BLURB: Record<string, string> = {
  notes: "Find every note. No metronome yet.",
  thread: "Connect them into a line. Still no metronome.",
  rhythm: "Metronome on — get the hands lining up.",
  technique: "Isolate the part that breaks first.",
  transition: "Just the crossing between two bars.",
  pair: "Two bars, then four, then eight.",
  section: "Straight through, slowly.",
  tempo: "Up the metronome a rung at a time.",
  integration: "Play two finished sections as one.",
};

export default function PracticePage() {
  const { pieceId } = useParams<{ pieceId: string }>();
  const { session, loading } = useSession();
  const router = useRouter();

  const [title, setTitle] = useState("");
  const [pages, setPages] = useState<PageImage[]>([]);
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Viewing an earlier step via Back. Any feedback clears it.
  const [override, setOverride] = useState<Step | null>(null);
  const history = useRef<Step[]>([]);

  const [bpm, setBpm] = useState(60);
  const [beats, setBeats] = useState(4);
  const [ticking, setTicking] = useState(false);
  const [pushPast, setPushPast] = useState(false);
  const metronome = useRef<Metronome | null>(null);

  const struggles = useRef<Record<string, number>>({});
  const stepStarted = useRef(Date.now());
  const sessionSeconds = useRef(Date.now());

  const userId = session?.user?.id;
  const step = override ?? state?.action.step ?? null;
  const usedMetronome = useRef(false);

  // ---- metronome lifecycle -------------------------------------------------

  useEffect(() => {
    metronome.current = new Metronome();
    return () => metronome.current?.dispose();
  }, []);

  useEffect(() => {
    if (!step) return;
    stepStarted.current = Date.now();
    usedMetronome.current = false;
    setPushPast(false);
    setBpm(step.target_tempo ?? 60);
    // The gate: notes and thread have no tempo to keep yet.
    if (step.metronome === "off") {
      metronome.current?.stop();
      setTicking(false);
    }
  }, [step?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!metronome.current) return;
    metronome.current.bpm = bpm;
    metronome.current.beatsPerBar = beats;
  }, [bpm, beats]);

  const toggleMetronome = () => {
    const m = metronome.current;
    if (!m) return;
    if (m.running) {
      m.stop();
      setTicking(false);
    } else {
      m.start();
      usedMetronome.current = true;
      setTicking(true);
    }
  };

  // ---- session -------------------------------------------------------------

  const apply = useCallback((next: State) => {
    setState(next);
    setOverride(null);
    if (next.action.step) history.current = [...history.current, next.action.step].slice(-20);
  }, []);

  useEffect(() => {
    if (!session || !pieceId) return;
    let cancelled = false;

    (async () => {
      const { data } = await supabase
        .from("pieces")
        .select("title, page_images")
        .eq("id", pieceId)
        .single();
      if (cancelled) return;
      if (data) {
        setTitle(data.title);
        setPages(data.page_images ?? []);
      }

      const res = await fetch(`${BACKEND_URL}/practice/session/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: session.user.id, piece_id: pieceId }),
      });
      if (cancelled) return;
      if (!res.ok) {
        setError("Couldn't start a practice session.");
        return;
      }
      apply(await res.json());
    })();

    return () => {
      cancelled = true;
    };
  }, [session, pieceId, apply]);

  // Leaving the page closes the session. A normal fetch is killed on unload,
  // so this has to be a beacon.
  useEffect(() => {
    const close = () => {
      const id = state?.session_id;
      if (!id) return;
      const seconds = Math.round((Date.now() - sessionSeconds.current) / 1000);
      navigator.sendBeacon(
        `${BACKEND_URL}/practice/session/end`,
        new Blob([JSON.stringify({ session_id: id, total_seconds: seconds })], {
          type: "application/json",
        })
      );
    };
    window.addEventListener("pagehide", close);
    return () => {
      window.removeEventListener("pagehide", close);
      close();
    };
  }, [state?.session_id]);

  const post = async (path: string, body: object, label: string) => {
    setBusy(label);
    try {
      const res = await fetch(`${BACKEND_URL}/practice/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (data.error) setError(data.error);
      else apply(data);
    } catch {
      setError("Lost the connection to the coach.");
    } finally {
      setBusy(null);
    }
  };

  const base = () => ({
    session_id: state?.session_id,
    user_id: userId,
    piece_id: pieceId,
    section_id: step?.section_id,
  });

  const report = (self_report: "nailed" | "shaky") =>
    post(
      "attempt",
      {
        ...base(),
        step_key: step!.key,
        stage: step!.stage,
        self_report,
        tempo_reached: usedMetronome.current ? bpm : null,
        target_tempo: step!.target_tempo,
        metronome_on: usedMetronome.current,
        seconds: Math.round((Date.now() - stepStarted.current) / 1000),
      },
      self_report
    );

  const struggle = () => {
    struggles.current[step!.key] = (struggles.current[step!.key] ?? 0) + 1;
    post("struggling", { ...base(), step_key: step!.key, stage: step!.stage }, "struggling");
  };

  const skip = () =>
    post("skip_stage", { ...base(), stage: step!.stage }, "skip");

  const goBack = () => {
    const previous = history.current[history.current.length - 2];
    if (previous) setOverride(previous);
  };

  // ---- render --------------------------------------------------------------

  if (loading || (!state && !error)) {
    return (
      <main className="min-h-screen bg-zinc-950 px-6 py-12">
        <div className="mx-auto h-64 max-w-5xl animate-pulse rounded-[2rem] bg-zinc-900" />
      </main>
    );
  }

  const action = state?.action;
  const secondTap = step ? (struggles.current[step.key] ?? 0) > 0 : false;
  const locked = step?.metronome === "off";
  const rungCap = step?.target_tempo ?? 120;
  const maxBpm = pushPast ? Math.round(rungCap * 1.3) : Math.max(rungCap, 60);

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-white">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
        <div className="flex items-center justify-between gap-4">
          <button
            onClick={() => router.push(`/piece/${pieceId}`)}
            className="text-sm text-zinc-400 hover:text-white cursor-pointer"
          >
            ← {title || "Back to piece"}
          </button>
          {action?.why && <p className="text-xs text-zinc-500">{action.why}</p>}
        </div>

        {error && (
          <div className="rounded-2xl border border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-300">
            {error}
          </div>
        )}

        <div className="grid gap-6 md:grid-cols-[15rem_1fr]">
          {/* Contents + the stage rail */}
          <aside className="flex flex-col gap-5 rounded-[2rem] border border-white/10 bg-zinc-900/80 p-5">
            <div className="flex flex-col gap-1.5">
              {state?.sections.map((s, i) => {
                const current = s.id === action?.section_id;
                return (
                  <div
                    key={s.id}
                    className={`rounded-xl px-3 py-2 text-sm ${
                      current ? "bg-indigo-500/15 text-white" : "text-zinc-400"
                    }`}
                    title={s.locked ? "Unlocks once the section before it is paired up" : undefined}
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-4 shrink-0 text-xs">
                        {s.complete ? "✓" : current ? "▶" : s.locked ? "🔒" : ""}
                      </span>
                      <span className="truncate">
                        {i + 1}. {s.title}
                      </span>
                    </div>
                    <div className="mt-1.5 ml-6 h-1 overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className="h-full rounded-full bg-indigo-400"
                        style={{ width: `${s.mastery}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {(state?.stages.length ?? 0) > 0 && (
              <div className="flex flex-col gap-1 border-t border-white/10 pt-4">
                {state!.stages.map((s) => {
                  const current = s.stage === step?.stage;
                  return (
                    <div
                      key={s.stage}
                      className={`flex items-center gap-2 rounded-lg px-2 py-1 text-xs ${
                        current ? "bg-white/5 text-white" : s.complete ? "text-zinc-500" : "text-zinc-600"
                      }`}
                    >
                      <span className="w-3">{s.complete ? "✓" : current ? "▶" : "○"}</span>
                      <span className="flex-1 truncate">{STAGE_LABEL[s.stage] ?? s.stage}</span>
                      <span className="tabular-nums">
                        {s.done}/{s.total}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </aside>

          {/* The step */}
          <section className="flex flex-col gap-5 rounded-[2rem] border border-white/10 bg-zinc-900/80 p-6">
            {!step ? (
              <div className="py-16 text-center">
                <p className="text-2xl font-semibold">
                  {action?.kind === "run_through"
                    ? "Every section is at tempo."
                    : "Nothing queued right now."}
                </p>
                <p className="mt-2 text-sm text-zinc-400">{action?.why}</p>
              </div>
            ) : (
              <>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-indigo-300">
                    {action?.section_title} · {STAGE_LABEL[step.stage] ?? step.stage}
                    {step.source === "remediation" && " · breakdown"}
                  </p>
                  <h1 className="mt-1 text-2xl font-semibold">{step.title}</h1>
                  <p className="mt-0.5 text-sm text-zinc-500">
                    {STAGE_BLURB[step.stage]}
                  </p>
                </div>

                {pages.length > 0 && (
                  <ScorePages
                    pages={pages}
                    fromMeasure={step.focus_start_measure}
                    toMeasure={step.focus_end_measure}
                  />
                )}

                <p className="text-sm leading-relaxed text-zinc-300">{step.description}</p>

                {/* Metronome. Locked until the notes are learned — this is the
                    whole point of the ladder, so it says why rather than just
                    greying out. */}
                <div className="rounded-2xl bg-zinc-800/50 p-4">
                  {locked ? (
                    <p className="text-sm text-zinc-500">
                      🔇 Metronome comes in at the rhythm stage — you can&apos;t click to
                      notes you don&apos;t have yet.
                    </p>
                  ) : (
                    <div className="flex flex-wrap items-center gap-4">
                      <button
                        onClick={toggleMetronome}
                        className={`rounded-xl px-4 py-2 text-sm font-semibold cursor-pointer ${
                          ticking
                            ? "bg-indigo-500 text-white"
                            : "bg-zinc-700 text-zinc-200 hover:bg-zinc-600"
                        }`}
                      >
                        {ticking ? "■ Stop" : "▶ Metronome"}
                      </button>
                      <span className="tabular-nums text-lg font-semibold">♩ {bpm}</span>
                      <input
                        type="range"
                        min={40}
                        max={maxBpm}
                        value={Math.min(bpm, maxBpm)}
                        onChange={(e) => setBpm(Number(e.target.value))}
                        className="h-1 flex-1 min-w-[8rem] cursor-pointer accent-indigo-400"
                      />
                      <select
                        value={beats}
                        onChange={(e) => setBeats(Number(e.target.value))}
                        className="rounded-lg bg-zinc-700 px-2 py-1 text-sm cursor-pointer"
                      >
                        <option value={4}>4/4</option>
                        <option value={3}>3/4</option>
                        <option value={6}>6/8</option>
                        <option value={2}>2/4</option>
                      </select>
                      {step.stage === "tempo" && !pushPast && (
                        <button
                          onClick={() => setPushPast(true)}
                          className="text-xs text-zinc-500 underline hover:text-zinc-300 cursor-pointer"
                        >
                          push past target
                        </button>
                      )}
                      {step.metronome === "required" && (
                        <span className="text-xs text-zinc-500">target {step.target_tempo}</span>
                      )}
                    </div>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={struggle}
                    disabled={!!busy}
                    className="rounded-2xl bg-zinc-800 px-5 py-3 text-sm font-semibold text-zinc-200 transition hover:bg-zinc-700 disabled:opacity-50 cursor-pointer"
                  >
                    {busy === "struggling"
                      ? secondTap
                        ? "Breaking this down…"
                        : "Narrowing…"
                      : "Struggling"}
                  </button>
                  <button
                    onClick={() => report("shaky")}
                    disabled={!!busy}
                    className="rounded-2xl bg-zinc-800 px-5 py-3 text-sm font-semibold text-zinc-200 transition hover:bg-zinc-700 disabled:opacity-50 cursor-pointer"
                  >
                    Shaky
                  </button>
                  <button
                    onClick={() => report("nailed")}
                    disabled={!!busy}
                    className="rounded-2xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 disabled:opacity-50 cursor-pointer"
                  >
                    Nailed it →
                  </button>

                  <div className="ml-auto flex items-center gap-3">
                    {(step.stage === "notes" || step.stage === "thread") && (
                      <button
                        onClick={skip}
                        disabled={!!busy}
                        className="text-xs text-zinc-500 underline hover:text-zinc-300 disabled:opacity-50 cursor-pointer"
                      >
                        I already know this
                      </button>
                    )}
                    {history.current.length > 1 && (
                      <button
                        onClick={goBack}
                        className="text-xs text-zinc-500 hover:text-zinc-300 cursor-pointer"
                      >
                        ← back
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
