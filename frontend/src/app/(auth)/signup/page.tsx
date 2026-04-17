"use client";

import { useState, useEffect } from "react";
import useSession from "@/lib/userSession";
import { useRouter } from "next/navigation";
import { signInWithGoogle } from "@/lib/auth";
import { supabase } from "@/lib/supabaseClient";
import { redirectAfterAuth } from "@/lib/auth";

export default function SignUpPage() {
  const { session, loading } = useSession();
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [formLoading, setFormLoading] = useState(false);

  useEffect(() => {
    if (!loading && !formLoading && session) {
      router.replace("/");
    }
  }, [session, loading, formLoading, router]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setFormLoading(true);

    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: name },
      },
    });

    if (error) {
      setError(error.message);
      setFormLoading(false);
      return;
    }

    // router.push("/callback");
    await redirectAfterAuth(router);
  }

  const handleGoogleAuth = () => {
    setFormLoading(true);
    signInWithGoogle();
  }

  if (loading) {
    return null
  }

  return (
    <main className="min-h-screen bg-zinc-950 text-white flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-zinc-900/90 p-8 shadow-xl shadow-black/20 backdrop-blur-md">
        <h1 className="text-3xl font-semibold">Sign up</h1>
        <p className="mt-2 text-sm text-zinc-400">Create an account and save your practice progress.</p>

        <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
          <label className="block text-sm font-medium text-zinc-200">
            Name
            <input
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              className="mt-2 w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-white outline-none transition focus:border-indigo-500"
            />
          </label>

          <label className="block text-sm font-medium text-zinc-200">
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              className="mt-2 w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-white outline-none transition focus:border-indigo-500"
            />
          </label>

          <label className="block text-sm font-medium text-zinc-200">
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              className="mt-2 w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-white outline-none transition focus:border-indigo-500"
            />
          </label>

          <button
            type="submit"
            disabled={formLoading}
            className="w-full rounded-2xl bg-indigo-500 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 cursor-pointer"
          >
            Create account
          </button>
        </form>

        {error ? <p className="mt-4 text-sm text-rose-400">{error}</p> : null}

        <div className="mt-6 space-y-3">
          <button
            type="button"
            onClick={handleGoogleAuth}
            className="w-full rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-zinc-100 cursor-pointer"
          >
            Continue with Google
          </button>
        </div>

        <p className="mt-6 text-center text-sm text-zinc-400">
          Already have an account?{' '}
          <button
            type="button"
            onClick={() => router.push("/signin")}
            className="font-semibold text-white underline underline-offset-4 hover:text-indigo-300 cursor-pointer"
          >
            Sign in
          </button>
        </p>

        <p className="mt-3 text-center text-sm text-zinc-500">
          <button
            type="button"
            onClick={() => router.push("/")}
            className="hover:text-indigo-300 cursor-pointer"
          >
            Back to home
          </button>
        </p>
      </div>
    </main>
  );
}
