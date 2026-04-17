"use client";

import Link from "next/link";

export default function PracticePlanPage() {
  // TODO: This would normally receive the uploaded file data and generated plan
  // For now, showing a placeholder

  return (
    <main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
        <div className="text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-white">Your Practice Plan</h1>
          <p className="mt-4 text-lg text-zinc-400">
            AI-generated practice plan for your uploaded sheet music.
          </p>
        </div>

        <div className="rounded-[2rem] border border-white/10 bg-zinc-900/90 p-8">
          <div className="space-y-6">
            <div className="text-center">
              <div className="text-6xl mb-4">🎼</div>
              <h2 className="text-2xl font-semibold text-white">Analysis Complete!</h2>
              <p className="mt-2 text-zinc-400">
                Your practice plan is being generated. This feature will be implemented in the next phase.
              </p>
            </div>

            <div className="space-y-4">
              <div className="rounded-xl bg-zinc-800/50 p-4">
                <h3 className="font-medium text-white">Coming Soon:</h3>
                <ul className="mt-2 space-y-1 text-sm text-zinc-400">
                  <li>• Section breakdowns</li>
                  <li>• Tempo suggestions</li>
                  <li>• Targeted drills</li>
                  <li>• Difficulty heatmaps</li>
                  <li>• Progress tracking</li>
                </ul>
              </div>
            </div>

            <div className="flex justify-center gap-4">
              <Link
                href="/upload"
                className="rounded-2xl bg-zinc-800 px-6 py-3 text-sm font-semibold text-white transition hover:bg-zinc-700"
              >
                Upload Another Piece
              </Link>
              <Link
                href="/"
                className="rounded-2xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400"
              >
                Back to Home
              </Link>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}