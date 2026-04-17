"use client";

import { supabase } from "@/lib/supabaseClient";
import useSession from "@/lib/userSession";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function OnboardingPage() {
  const { session, loading } = useSession();
  const router = useRouter();
  const [level, setLevel] = useState<string | null>(null);
  const [yoe, setYoe] = useState<string>("");
  const [formLoading, setFormLoading] = useState(false);
  const name = session?.user?.user_metadata?.full_name || "Account";

  const isValid = level !== null && yoe !== "";

  useEffect(() => {
    const run = async () => {
      if (loading) return;

      if (!session) {
        router.replace("/");
        return;
      }

      const { data: profile } = await supabase
        .from("profiles")
        .select("onboarding_complete")
        .eq("id", session.user.id)
        .single();

      if (profile?.onboarding_complete) {
        router.replace("/profile");
        return;
      }
    };

    run();
  }, [session, loading, router]);

  const handleSubmit = async () => {
    if (!isValid || !session) return;

    setFormLoading(true);

    const res = await fetch("/api/onboarding", {
      method: "POST",
      body: JSON.stringify({
        userId: session.user.id,
        level,
        years: parseInt(yoe, 10),
      }),
    });

    setFormLoading(false);

    if (res.ok) {
      router.push("/profile");
    } else {
      console.error(await res.json());
    }
  };

  if (loading || !session) {
    return null;
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        <section>
          <div>
            <p className="text-xl uppercase tracking-[0.3em] text-indigo-300">Hello, {name}</p>
          </div>
        </section>

        <section>
          <div className="mt-10 space-y-4">
            {/* Piano Level */}
            <div>
              <p className="text-xs uppercase tracking-widest text-zinc-500 mb-2">
                What is you piano level?
              </p>

              <div className="flex gap-2">
                {["Beginner", "Intermediate", "Advanced"].map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setLevel(option.toLowerCase())}
                    className={`px-4 py-2 rounded-xl text-sm font-medium border transition cursor-pointer
                  ${level === option.toLowerCase()
                        ? "bg-indigo-500 text-white border-indigo-500"
                        : "bg-zinc-900 text-zinc-300 border-zinc-700 hover:bg-zinc-800"
                      }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>

            {/* Years of Experience */}
            <div className="mt-10">
              <p className="text-xs uppercase tracking-widest text-zinc-500 mb-2">
                How many years of experience do you have?
              </p>

              <input
                type="number"
                min="0"
                placeholder="0"
                value={yoe}
                onChange={(e) => setYoe(e.target.value)}
                className="w-24 rounded-xl bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
              />
            </div>

            {/* Submit */}
            <div className="pt-4">
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!isValid || formLoading}
                className={`rounded-2xl px-6 py-3 text-sm font-semibold transition cursor-pointer
                  ${
                    isValid
                      ? "bg-indigo-500 text-white hover:bg-indigo-400"
                      : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                  }`}
              >
                {formLoading ? "Saving..." : "Continue"}
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
