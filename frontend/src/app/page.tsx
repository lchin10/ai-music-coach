"use client";

import useSession from "@/lib/userSession";
import { useRouter } from "next/navigation";

export default function Home() {
  const { session, loading } = useSession();
  const router = useRouter();

  if (loading) {
    return null
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-12 px-6 py-12">
        <section className="rounded-[2rem] border border-white/10 bg-zinc-900/90 p-10 shadow-xl shadow-black/30 backdrop-blur-xl">
          <div className="max-w-3xl space-y-6">
            <p className="text-sm uppercase tracking-[0.3em] text-indigo-300">AI music coach</p>
            <h1 className="text-5xl font-semibold tracking-tight text-white sm:text-6xl">
              Practice smarter with AI-driven music coaching.
            </h1>
            <p className="max-w-2xl text-lg leading-8 text-zinc-300">
              Upload sheet music, generate a tailored practice plan, and track every session with progress memory built for real musicians.
            </p>

            <div className="flex flex-wrap gap-4">
              {session ? (
                <>
                  {/* "Your pieces" rather than "Start practising" — this goes
                      to the library, and a session starts from a piece. */}
                  <button
                    type="button"
                    onClick={() => router.push("/profile")}
                    className="inline-flex items-center justify-center rounded-2xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 cursor-pointer"
                  >
                    Your pieces →
                  </button>
                  <button
                    type="button"
                    onClick={() => router.push("/upload")}
                    className="inline-flex items-center justify-center rounded-2xl bg-zinc-800 px-6 py-3 text-sm font-semibold text-white transition hover:bg-zinc-700 cursor-pointer"
                  >
                    Upload a piece
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => router.push("/signup")}
                  className="inline-flex items-center justify-center rounded-2xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 cursor-pointer"
                >
                  Get started
                </button>
              )}
            </div>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-3">
          <div className="rounded-[2rem] border border-white/10 bg-zinc-900/90 p-8 text-zinc-100 shadow-lg shadow-black/20">
            <h2 className="text-2xl font-semibold">Upload sheet music</h2>
            <p className="mt-3 text-sm text-zinc-400">
              Drop a PDF file and let the app analyze it with music theory and OMR-aware logic.
            </p>
          </div>
          <div className="rounded-[2rem] border border-white/10 bg-zinc-900/90 p-8 text-zinc-100 shadow-lg shadow-black/20">
            <h2 className="text-2xl font-semibold">Personalized practice plans</h2>
            <p className="mt-3 text-sm text-zinc-400">
              Receive section breakdowns, tempo suggestions, and targeted drills for the hardest passages.
            </p>
          </div>
          <div className="rounded-[2rem] border border-white/10 bg-zinc-900/90 p-8 text-zinc-100 shadow-lg shadow-black/20">
            <h2 className="text-2xl font-semibold">Track progress</h2>
            <p className="mt-3 text-sm text-zinc-400">
              Start, stop, and resume practice sessions with persistent data so every session counts.
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}
