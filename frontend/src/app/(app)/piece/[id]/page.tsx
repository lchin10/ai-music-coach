"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import useSession from "@/lib/userSession";

type Piece = {
  id: string;
  title: string;
  status: string;
  created_at: string;
};

type Section = {
  id: string;
  title: string;
  start_measure: number;
  end_measure: number;
  difficulty: number;
  notes: string;
  analysis_data: {
    key_challenges?: string[];
    techniques?: string[];
    musical_character?: string;
  } | null;
};

type PlanStep = {
  id: string;
  section_id: string;
  order_index: number;
  title: string;
  description: string;
  target_tempo: number;
  drill_type: string;
  is_checkpoint: boolean;
  unlock_requirement: number;
};

function DifficultyBadge({ difficulty }: { difficulty: number }) {
  const label =
    difficulty < 25 ? "Easy" : difficulty < 50 ? "Moderate" : difficulty < 75 ? "Hard" : "Expert";
  const color =
    difficulty < 25
      ? "text-emerald-400 bg-emerald-400/10 border-emerald-400/20"
      : difficulty < 50
      ? "text-yellow-400 bg-yellow-400/10 border-yellow-400/20"
      : difficulty < 75
      ? "text-orange-400 bg-orange-400/10 border-orange-400/20"
      : "text-rose-400 bg-rose-400/10 border-rose-400/20";
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${color}`}>
      {label} · {difficulty}
    </span>
  );
}

const DRILL_LABELS: Record<string, string> = {
  hands_separate: "Hands separate",
  hands_together: "Hands together",
  loop: "Loop",
  slow_practice: "Slow practice",
  tempo_building: "Tempo building",
  rhythm_variation: "Rhythm variation",
  metronome: "Metronome",
  articulation_focus: "Articulation",
  checkpoint: "Checkpoint",
};

export default function PiecePage() {
  const { id } = useParams<{ id: string }>();
  const { session, loading } = useSession();
  const router = useRouter();

  const [piece, setPiece] = useState<Piece | null>(null);
  const [sections, setSections] = useState<Section[]>([]);
  const [steps, setSteps] = useState<PlanStep[]>([]);
  const [pageLoading, setPageLoading] = useState(true);

  useEffect(() => {
    if (!session || !id) return;

    const fetchData = async () => {
      const [pieceRes, sectionsRes, planRes] = await Promise.all([
        supabase.from("pieces").select("id, title, status, created_at").eq("id", id).single(),
        supabase.from("sections").select("*").eq("piece_id", id).order("start_measure"),
        supabase.from("practice_plans").select("id").eq("piece_id", id).maybeSingle(),
      ]);

      if (pieceRes.data) setPiece(pieceRes.data);
      if (sectionsRes.data) setSections(sectionsRes.data);

      if (planRes.data) {
        const { data: stepsData } = await supabase
          .from("plan_steps")
          .select("*")
          .eq("plan_id", planRes.data.id)
          .order("order_index");
        if (stepsData) setSteps(stepsData);
      }

      setPageLoading(false);
    };

    fetchData();
  }, [session, id]);

  if (loading || pageLoading) return null;

  if (!piece) {
    return (
      <main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
        <p className="text-zinc-400 text-center">Piece not found.</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
        {/* Header */}
        <div>
          <button
            onClick={() => router.push("/profile")}
            className="mb-4 text-sm text-zinc-400 hover:text-white cursor-pointer"
          >
            ← Back to profile
          </button>
          <h1 className="text-3xl font-semibold text-white leading-tight">{piece.title}</h1>
          <p className="mt-1 text-sm text-zinc-400">
            {sections.length} section{sections.length !== 1 ? "s" : ""} · {steps.length} practice step{steps.length !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Sections */}
        {sections.length === 0 ? (
          <p className="text-zinc-400">No sections found for this piece.</p>
        ) : (
          <div className="flex flex-col gap-6">
            {sections.map((section) => {
              const sectionSteps = steps
                .filter((s) => s.section_id === section.id)
                .sort((a, b) => a.order_index - b.order_index);

              return (
                <div
                  key={section.id}
                  className="rounded-[2rem] border border-white/10 bg-zinc-900/90 p-8"
                >
                  {/* Section header */}
                  <div className="flex items-start justify-between gap-4 mb-5">
                    <div>
                      <h2 className="text-xl font-semibold text-white">{section.title}</h2>
                      <p className="mt-1 text-sm text-zinc-400">
                        Measures {section.start_measure}–{section.end_measure}
                      </p>
                      {section.notes && (
                        <p className="mt-2 text-sm text-zinc-300">{section.notes}</p>
                      )}
                    </div>
                    <DifficultyBadge difficulty={section.difficulty} />
                  </div>

                  {/* Key challenges */}
                  {(section.analysis_data?.key_challenges?.length ?? 0) > 0 && (
                    <div className="mb-5 flex flex-wrap gap-2">
                      {section.analysis_data!.key_challenges!.map((c) => (
                        <span
                          key={c}
                          className="rounded-full bg-zinc-800 px-3 py-1 text-xs text-zinc-300"
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Steps */}
                  {sectionSteps.length > 0 && (
                    <div className="flex flex-col gap-3">
                      {sectionSteps.map((step, i) => (
                        <div
                          key={step.id}
                          className={`rounded-2xl p-4 ${
                            step.is_checkpoint
                              ? "border border-indigo-500/40 bg-indigo-500/5"
                              : "bg-zinc-800/50"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex gap-3">
                              <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-zinc-700 text-xs font-bold text-zinc-300">
                                {i + 1}
                              </span>
                              <div>
                                <p className="text-sm font-medium text-white">{step.title}</p>
                                <p className="mt-1 text-xs text-zinc-400">{step.description}</p>
                              </div>
                            </div>
                            <div className="flex shrink-0 flex-col items-end gap-1">
                              <span className="text-xs font-semibold text-indigo-300">
                                {step.target_tempo} bpm
                              </span>
                              <span className="rounded-full bg-zinc-700 px-2 py-0.5 text-xs text-zinc-400">
                                {DRILL_LABELS[step.drill_type] ?? step.drill_type}
                              </span>
                            </div>
                          </div>
                          {step.unlock_requirement > 0 && (
                            <p className="ml-9 mt-2 text-xs text-zinc-500">
                              Unlocks at {step.unlock_requirement}% mastery
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
