"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabaseClient";

export type PageImage = {
  page: number;
  start_measure: number;
  end_measure: number;
  path: string;
  /** False when the system couldn't be isolated and the whole page is shown. */
  cropped?: boolean;
};

type Props = {
  pages: PageImage[];
  fromMeasure: number;
  toMeasure: number;
};

/**
 * Shows the staff systems covering a measure range, cropped from the PDF.
 *
 * This is the real engraving rather than a re-render of the OMR output —
 * Audiveris drops fingerings, most dynamics and, on dense scores, notes, so a
 * re-render shows music that doesn't match the page the user is playing from.
 */
/** A page and the signed URL that belongs to it — never two loose arrays. */
type Signed = PageImage & { url: string };

export default function ScorePages({ pages, fromMeasure, toMeasure }: Props) {
  // Each image carries its own URL. Holding the URLs in a separate array and
  // matching by index crashed: `pages` is derived from props and updates
  // immediately, while the URLs are state and lag a render, so on a step
  // change the shorter new list was indexed with the older, longer one.
  const [signed, setSigned] = useState<Signed[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // A page is relevant when its measures overlap the requested range.
  const relevant = pages
    .filter((p) => p.end_measure >= fromMeasure && p.start_measure <= toMeasure)
    .sort((a, b) => a.page - b.page);

  const key = relevant.map((p) => p.path).join("|");

  useEffect(() => {
    if (relevant.length === 0) {
      setSigned([]);
      return;
    }

    let cancelled = false;
    // Drop the previous step's images rather than showing them under the new
    // caption while these sign.
    setSigned(null);
    setError(null);

    (async () => {
      const { data, error: signError } = await supabase.storage
        .from("pieces")
        .createSignedUrls(
          relevant.map((p) => p.path),
          3600
        );

      if (cancelled) return;
      if (signError || !data) {
        setError(signError?.message ?? "Could not load the score");
        return;
      }

      // Pair by path, which the API echoes back — order and length can't
      // drift the way index matching did.
      const byPath = new Map(
        data.filter((d) => d.path && d.signedUrl).map((d) => [d.path as string, d.signedUrl])
      );
      setSigned(
        relevant
          .filter((p) => byPath.has(p.path))
          .map((p) => ({ ...p, url: byPath.get(p.path)! }))
      );
    })();

    return () => {
      cancelled = true;
    };
    // `key` covers the identity of the pages being shown.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (relevant.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-zinc-800/40 p-4 text-xs text-zinc-500">
        No page image covers measures {fromMeasure}–{toMeasure}.
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-white/10 bg-zinc-800/40 p-4 text-xs text-zinc-500">
        Score unavailable — {error}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {!signed && <div className="h-64 animate-pulse rounded-2xl bg-zinc-800/50" />}
      {signed?.map((page) => (
        <figure key={page.path} className="overflow-hidden rounded-2xl bg-white">
          {/* Sheet music is engraved black-on-white; a white surface is what
              it's meant to be read on, and inverting it hurts legibility. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={page.url}
            alt={`Measures ${page.start_measure}–${page.end_measure}`}
            className="w-full"
            loading="lazy"
          />
          <figcaption className="bg-zinc-100 px-3 py-1.5 text-xs text-zinc-600">
            mm. {page.start_measure}–{page.end_measure}
            {page.cropped === false && ` · full page ${page.page + 1}`}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}
