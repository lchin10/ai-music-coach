"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabaseClient";

type Props = {
  /** `pieces.file_path` — the original uploaded PDF. */
  filePath: string | null;
  /** Open on first render. Off by default: it's a reference, not the subject. */
  defaultOpen?: boolean;
};

/**
 * The whole piece, on demand.
 *
 * The cropped system images answer "which bars am I drilling"; this answers
 * "where am I in the piece". It's the original PDF rather than anything
 * rendered, so it has the fingerings and dynamics the OMR dropped.
 *
 * The URL is only signed once the panel is actually opened — a signed link per
 * piece card on a page that shows several would be wasted round trips.
 */
export default function FullScore({ filePath, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || url || !filePath) return;
    let cancelled = false;

    (async () => {
      const { data, error: signError } = await supabase.storage
        .from("pieces")
        .createSignedUrl(filePath, 3600);
      if (cancelled) return;
      if (signError || !data) setError(signError?.message ?? "Could not load the score");
      else setUrl(data.signedUrl);
    })();

    return () => {
      cancelled = true;
    };
  }, [open, url, filePath]);

  if (!filePath) return null;

  return (
    <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-zinc-900/90">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 p-5 text-left transition hover:bg-white/5 cursor-pointer"
      >
        <span className={`text-zinc-500 transition-transform ${open ? "rotate-90" : ""}`} aria-hidden>
          ▸
        </span>
        <span className="flex-1 text-sm font-semibold text-white">Full score</span>
        <span className="text-xs text-zinc-500">{open ? "Hide" : "Show the whole piece"}</span>
      </button>

      {open && (
        <div className="border-t border-white/10">
          {error ? (
            <p className="p-5 text-xs text-zinc-500">Score unavailable — {error}</p>
          ) : url ? (
            <>
              {/* The browser's own PDF viewer: paging, zoom and search for free. */}
              <iframe
                src={url}
                title="Full score"
                className="h-[80vh] w-full bg-white"
              />
              <div className="px-5 py-2 text-right">
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs text-zinc-500 underline hover:text-zinc-300"
                >
                  Open in a new tab
                </a>
              </div>
            </>
          ) : (
            <div className="h-64 animate-pulse bg-zinc-800/50" />
          )}
        </div>
      )}
    </div>
  );
}
