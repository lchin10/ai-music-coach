"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useRef } from "react";
import { supabase } from "@/lib/supabaseClient";
import useSession from "@/lib/userSession";

export function Header() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  const name = session?.user?.user_metadata?.full_name || "Account";

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const signOut = async () => {
    await supabase.auth.signOut({ scope: "local" });
    router.push('/')
  }

  if (loading) {
    return null
  }

  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-zinc-950/90 px-6 py-4 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4">
        <div className="text-lg font-semibold uppercase tracking-[0.3em] text-white">
          <button
            type="button"
            onClick={() => router.push("/")}
            className="cursor-pointer"
          >
            AI PIANO PRACTICE
          </button>
        </div>

      <div className="flex items-center gap-3">
        {session ? (
          <div className="relative" ref={dropdownRef}>
            <button
              type="button"
              onClick={() => setIsOpen((current) => !current)}
              className="inline-flex items-center gap-2 rounded-2xl border border-zinc-700 bg-zinc-900/80 px-4 py-2 text-sm font-semibold text-white transition hover:border-indigo-400 cursor-pointer"
            >
              <span>{name}</span>
              <span className="text-zinc-400">▾</span>
            </button>

            {isOpen ? (
              <div className="absolute right-0 mt-2 w-48 rounded-3xl border border-white/10 bg-zinc-900/95 p-2 shadow-xl shadow-black/50">
                <button
                  type="button"
                  onClick={() => {
                    setIsOpen(false);
                    router.push("/profile");
                  }}
                  className="block w-full rounded-2xl px-4 py-3 text-left text-sm text-zinc-200 transition hover:bg-zinc-800 cursor-pointer"
                >
                  Profile
                </button>
                <button
                  type="button"
                  onClick={signOut}
                  className="mt-1 w-full rounded-2xl px-4 py-3 text-left text-sm text-zinc-200 transition hover:bg-zinc-800 cursor-pointer"
                >
                  Logout
                </button>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => router.push("/signin")}
              className="rounded-2xl border border-zinc-700 bg-zinc-900/80 px-4 py-2 text-sm font-semibold text-white transition hover:border-indigo-400 cursor-pointer"
            >
              Sign in
            </button>
            <button
              type="button"
              onClick={() => router.push("/signup")}
              className="rounded-2xl bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-400 cursor-pointer"
            >
              Sign up
            </button>
          </div>
        )}
      </div>
    </div>
    </header >
  );
}
