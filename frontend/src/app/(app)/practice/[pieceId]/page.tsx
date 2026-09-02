"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import useSession from "@/lib/userSession";
import ScorePages, { type PageImage } from "@/components/ScorePages";
import { Metronome } from "@/lib/metronome";
import { displayComposer, displayTitle } from "@/lib/pieceName";
import FullScore from "@/components/FullScore";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type Instruction = { lead: string; detail: string };

type Step = {
  key: string;
  section_id: string;
  stage: string;
  focus_start_measure: number;
  focus_end_measure: number;
  metronome: "off" | "optional" | "required";
  target_tempo: number | null;
  title: string;
  instructions: Instruction[] | null;
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

/** One rung in the rail: label and status only. The full step (instructions
 *  and all) is fetched from /practice/step when a rung is actually opened. */
type Rung = {
  key: string;
  label: string;
  title: string;
  /** Position in the ladder's true order, which interleaves transitions and
   *  pairs even though the rail groups them by stage. */
  order: number;
  done: boolean;
  visited: boolean;
};

type StageRow = {
  stage: string;
  total: number;
  done: number;
  complete: boolean;
  steps: Rung[];
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
  stages: StageRow[];
};

type State = {
  session_id: string | null;
  action: Action;
  sections: SectionRow[];
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

  const [name, setName] = useState({ title: "", composer: "" });
  const [filePath, setFilePath] = useState<string | null>(null);
  const [pages, setPages] = useState<PageImage[]>([]);
  const [railOpen, setRailOpen] = useState(true);
  const [state, setState] = useState<State | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Every step shown this session, and where in it we're looking; null means
  // the live one from the server. A cursor rather than a single "previous
  // step" is what lets Back keep walking backwards — the old version always
  // read history[length - 2], so a second click went nowhere.
  const history = useRef<Step[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  // Which stage is expanded in the rail, and what the live stage was when the
  // choice was made — so the rail follows along once you move on, without a
  // setState-in-effect.
  const [stagePick, setStagePick] = useState<{
    section: string;
    stage: string | null;
    whenStage: string | null;
  } | null>(null);
  const [sectionPick, setSectionPick] = useState<string | null>(null);

  const [bpm, setBpm] = useState(60);
  const [beats, setBeats] = useState(4);
  const [ticking, setTicking] = useState(false);
  const [pushPast, setPushPast] = useState(false);
  const metronome = useRef<Metronome | null>(null);

  const struggles = useRef<Record<string, number>>({});
  const stepStarted = useRef(Date.now());
  const sessionSeconds = useRef(Date.now());

  const userId = session?.user?.id;
  const step = cursor !== null ? history.current[cursor] ?? null : state?.action.step ?? null;
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

  /** Show a step and record that it was visited. Consecutive duplicates are
   *  dropped so Back never lands on the step you're already looking at. */
  const remember = (next: Step) => {
    const last = history.current[history.current.length - 1];
    if (last?.key !== next.key) history.current = [...history.current, next];
    setCursor(null);
  };

  const apply = useCallback((next: State) => {
    setState(next);
    if (next.action.step) remember(next.action.step);
    else setCursor(null);
  }, []);

  useEffect(() => {
    if (!session || !pieceId) return;
    let cancelled = false;

    (async () => {
      const { data } = await supabase
        .from("pieces")
        .select("title, work_title, composer, page_images, file_path")
        .eq("id", pieceId)
        .single();
      if (cancelled) return;
      if (data) {
        setName({ title: displayTitle(data), composer: displayComposer(data) });
        setPages(data.page_images ?? []);
        setFilePath(data.file_path ?? null);
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

  // Every rung of the plan, in the order the ladder serves them. "Back a step"
  // walks THIS, not the order you happened to visit things in — going from
  // mm. 7-8 to mm. 3-4 and pressing back should land on mm. 1-2, not bounce
  // you to mm. 7-8.
  //
  // Sorted by `order` rather than taken as laid out, because the rail groups
  // transitions and pairs into separate stages while the ladder interleaves
  // them one merge level at a time.
  // Sections already arrive in playing order, so sorting each one's rungs and
  // concatenating gives the whole piece in ladder order.
  const planOrder = (state?.sections ?? []).flatMap((s) =>
    s.stages
      .flatMap((st) => st.steps)
      .sort((a, b) => a.order - b.order)
      .map((r) => r.key)
  );
  const planIndex = step ? planOrder.indexOf(step.key) : -1;
  // -1 covers a remediation drill, which isn't part of the plan — there's no
  // "previous rung" to step back to from one.
  const canGoBack = planIndex > 0;
  const goBack = () => openRung(planOrder[planIndex - 1]);

  /** Which stage is expanded for a section.
   *
   *  Defaults to the stage you're on, and follows along as you advance — but a
   *  deliberate pick wins until the live stage moves past it, which is why the
   *  pick records the stage it was made against instead of being reset by an
   *  effect.
   */
  const openStage = (sectionId: string) => {
    const live = sectionId === state?.action.section_id ? step?.stage ?? null : null;
    if (stagePick?.section === sectionId && stagePick.whenStage === live) {
      return stagePick.stage;
    }
    return live;
  };

  /** One stage open at a time: picking another closes the last. */
  const pickStage = (sectionId: string, stage: string) => {
    const live = sectionId === state?.action.section_id ? step?.stage ?? null : null;
    setStagePick({
      section: sectionId,
      stage: openStage(sectionId) === stage ? null : stage,
      whenStage: live,
    });
  };

  /** Jump to a rung from the rail. Only visited rungs are offered, so this is
   *  always revisiting, never skipping ahead. */
  const openRung = async (key: string) => {
    const known = history.current.findIndex((s) => s.key === key);
    if (known !== -1) {
      setCursor(known);
      return;
    }
    setBusy("rung");
    try {
      const res = await fetch(
        `${BACKEND_URL}/practice/step?user_id=${userId}&piece_id=${pieceId}` +
          `&step_key=${encodeURIComponent(key)}`
      );
      const data = await res.json();
      if (!data.step) throw new Error("missing");
      history.current = [...history.current, data.step];
      setCursor(history.current.length - 1);
    } catch {
      setError("Couldn't open that step.");
    } finally {
      setBusy(null);
    }
  };

  // ---- render --------------------------------------------------------------

  if (loading || (!state && !error)) {
    return (
      <main className="min-h-screen bg-zinc-950 p-6">
        <div className="h-64 animate-pulse rounded-[2rem] bg-zinc-900" />
      </main>
    );
  }

  const action = state?.action;
  const secondTap = step ? (struggles.current[step.key] ?? 0) > 0 : false;
  const locked = step?.metronome === "off";
  const rungCap = step?.target_tempo ?? 120;
  const maxBpm = pushPast ? Math.round(rungCap * 1.3) : Math.max(rungCap, 60);

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      {/* Header: the piece, not the filename. The back link is deliberately
          small — during a session the music is the subject, not navigation. */}
      <header className="flex items-start gap-4 border-b border-white/10 px-5 py-4">
        <button
          onClick={() => router.push(`/piece/${pieceId}`)}
          aria-label="Back to piece"
          className="mt-1 shrink-0 rounded-lg px-2 py-1 text-zinc-500 transition hover:bg-white/5 hover:text-white cursor-pointer"
        >
          ←
        </button>
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold leading-tight">
            {name.title || "Practice"}
          </h1>
          {name.composer && (
            <p className="truncate text-sm text-zinc-400">{name.composer}</p>
          )}
        </div>
        {action?.why && (
          <p className="ml-auto hidden shrink-0 self-center text-xs text-zinc-500 lg:block">
            {action.why}
          </p>
        )}
      </header>

      {error && (
        <div className="mx-5 mt-4 rounded-2xl border border-rose-500/30 bg-rose-500/5 p-4 text-sm text-rose-300">
          {error}
        </div>
      )}

      <div className="flex items-start gap-5 p-5">
        {!railOpen && (
          <button
            onClick={() => setRailOpen(true)}
            aria-label="Show contents"
            className="shrink-0 rounded-xl border border-white/10 bg-zinc-900/80 px-2.5 py-3 text-zinc-400 transition hover:text-white cursor-pointer"
          >
            ☰
          </button>
        )}

        {/* Contents + the stage rail, flush to the left edge. */}
        <aside
          className={`sticky top-5 flex-col gap-5 rounded-[2rem] border border-white/10 bg-zinc-900/80 p-5 ${
            railOpen ? "flex w-60 shrink-0" : "hidden"
          }`}
        >
          <button
            onClick={() => setRailOpen(false)}
            className="self-end text-xs text-zinc-500 hover:text-zinc-300 cursor-pointer"
          >
            ✕ hide
          </button>
          <div className="flex flex-col gap-1">
            {state?.sections.map((section, i) => {
              const current = section.id === action?.section_id;
              const open = current || sectionPick === section.id;
              return (
                <div key={section.id}>
                  {/* The current section always stays open; any one other
                      section can be pinned open alongside it. */}
                  <button
                    onClick={() =>
                      !current &&
                      !section.locked &&
                      setSectionPick(sectionPick === section.id ? null : section.id)
                    }
                    disabled={section.locked}
                    className={`w-full rounded-xl px-2.5 py-2 text-left text-sm transition ${
                      current
                        ? "bg-indigo-500/15 text-white"
                        : section.locked
                        ? "text-zinc-600"
                        : "text-zinc-400 hover:bg-white/5 cursor-pointer"
                    }`}
                    title={
                      section.locked
                        ? "Unlocks once the section before it is paired up"
                        : undefined
                    }
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-4 shrink-0 text-xs">
                        {section.complete ? "✓" : current ? "▶" : section.locked ? "🔒" : ""}
                      </span>
                      <span className="truncate">
                        {i + 1}. {section.title}
                      </span>
                    </div>
                    <div className="ml-6 mt-1.5 h-1 overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className="h-full rounded-full bg-indigo-400"
                        style={{ width: `${section.mastery}%` }}
                      />
                    </div>
                  </button>

                  {/* This section's ladder, directly underneath it. */}
                  {open && (
                    <div className="ml-3 mt-1 flex flex-col gap-0.5 border-l border-white/10 pl-2">
                      {section.stages.map((row) => {
                        const onStage = current && row.stage === step?.stage;
                        const expanded = openStage(section.id) === row.stage;
                        return (
                          <div key={row.stage}>
                            <button
                              onClick={() => pickStage(section.id, row.stage)}
                              className={`flex w-full items-center gap-1.5 rounded-lg px-1.5 py-1 text-xs transition hover:bg-white/5 cursor-pointer ${
                                onStage
                                  ? "text-white"
                                  : row.complete
                                  ? "text-zinc-500"
                                  : "text-zinc-600"
                              }`}
                            >
                              <span
                                className={`w-2.5 shrink-0 transition-transform ${
                                  expanded ? "rotate-90" : ""
                                }`}
                                aria-hidden
                              >
                                ▸
                              </span>
                              <span className="flex-1 truncate text-left">
                                {STAGE_LABEL[row.stage] ?? row.stage}
                              </span>
                              <span className="tabular-nums">
                                {row.done}/{row.total}
                              </span>
                            </button>

                            {/* The individual rungs. Only ones already
                                attempted are reachable — anything else would
                                be skipping ahead rather than revisiting. */}
                            {expanded && (
                              <div className="ml-4 flex flex-col">
                                {row.steps.map((rung) => {
                                  const here = rung.key === step?.key;
                                  return (
                                    <button
                                      key={rung.key}
                                      onClick={() => rung.visited && openRung(rung.key)}
                                      disabled={!rung.visited || !!busy}
                                      title={
                                        rung.visited
                                          ? rung.title
                                          : "You haven't reached this one yet"
                                      }
                                      className={`flex items-center gap-1.5 rounded px-1.5 py-0.5 text-left text-[11px] transition ${
                                        here
                                          ? "bg-white/10 text-white"
                                          : rung.visited
                                          ? "text-zinc-400 hover:bg-white/5 cursor-pointer"
                                          : "text-zinc-700"
                                      }`}
                                    >
                                      <span className="w-2.5 shrink-0">
                                        {rung.done ? "✓" : here ? "▸" : ""}
                                      </span>
                                      <span className="truncate">{rung.label}</span>
                                    </button>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </aside>

        {/* The step — takes whatever the rail leaves. */}
        <section className="flex min-w-0 flex-1 flex-col gap-5 rounded-[2rem] border border-white/10 bg-zinc-900/80 p-6">
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

                {/* Numbered, with the instruction bolded and the reasoning
                    underneath — mid-passage you glance at this, you don't
                    read it. */}
                {step.instructions?.length ? (
                  <ol className="flex list-none flex-col gap-3">
                    {step.instructions.map((point, i) => (
                      <li key={i} className="flex gap-3">
                        <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-xs font-bold text-zinc-400">
                          {i + 1}
                        </span>
                        <div className="min-w-0">
                          {point.lead && (
                            <p className="text-sm font-semibold text-white">{point.lead}</p>
                          )}
                          {point.detail && (
                            <p className="mt-0.5 text-sm leading-relaxed text-zinc-400">
                              {point.detail}
                            </p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-sm leading-relaxed text-zinc-300">{step.description}</p>
                )}

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

                <div className="flex flex-wrap items-start justify-between gap-4">
                  {/* Left: the two ways this can go wrong. */}
                  <div className="flex flex-col items-start gap-2">
                    <div className="flex flex-wrap gap-3">
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
                    </div>
                    {canGoBack && (
                      <button
                        onClick={goBack}
                        className="text-xs text-zinc-500 hover:text-zinc-300 cursor-pointer"
                      >
                        ← back a step
                      </button>
                    )}
                  </div>

                  {/* Right: the way forward. */}
                  <div className="flex flex-col items-end gap-2">
                    <button
                      onClick={() => report("nailed")}
                      disabled={!!busy}
                      className="rounded-2xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 disabled:opacity-50 cursor-pointer"
                    >
                      Nailed it →
                    </button>
                    {(step.stage === "notes" || step.stage === "thread") && (
                      <button
                        onClick={skip}
                        disabled={!!busy}
                        className="text-xs text-zinc-500 underline hover:text-zinc-300 disabled:opacity-50 cursor-pointer"
                      >
                        I already know this
                      </button>
                    )}
                  </div>
                </div>
              </>
            )}
        </section>
      </div>

      <div className="px-5 pb-5">
        <FullScore filePath={filePath} />
      </div>
    </main>
  );
}
