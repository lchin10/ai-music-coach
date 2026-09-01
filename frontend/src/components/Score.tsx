"use client";

import { useEffect, useRef, useState } from "react";
import type { OpenSheetMusicDisplay as OSMD } from "opensheetmusicdisplay";
import { toOsmdRange } from "@/lib/measures";

type Props = {
  /**
   * The score, fetched once by the page and shared across instances.
   * A Blob for compressed .mxl (what Audiveris emits), a string for plain XML —
   * both are accepted by OSMD's load().
   */
  xml: Blob | string | null;
  /** Our measure numbers — converted to OSMD's via measure_offset. */
  fromMeasure: number;
  toMeasure: number;
  measureOffset: number;
  zoom?: number;
};

/**
 * Renders a range of bars with OpenSheetMusicDisplay.
 *
 * OSMD touches window/DOM, so this must only ever be mounted client-side —
 * import it with next/dynamic and ssr:false. Mount one per *visible* section:
 * a 20-section piece rendering all at once is what makes the page crawl.
 */
export default function Score({
  xml,
  fromMeasure,
  toMeasure,
  measureOffset,
  zoom = 0.7,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const osmd = useRef<OSMD | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!xml || !container.current) return;

    let cancelled = false;
    const host = container.current;

    (async () => {
      try {
        const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
        if (cancelled) return;

        const range = toOsmdRange(fromMeasure, toMeasure, measureOffset);

        // Rebuild rather than reconfigure: OSMD re-renders a measure range
        // more reliably from a fresh instance than by mutating options.
        osmd.current?.clear();
        host.innerHTML = "";

        const instance = new OpenSheetMusicDisplay(host, {
          autoResize: false, // handled below, so a collapsed panel doesn't thrash
          backend: "svg",
          darkMode: true,
          drawTitle: false,
          drawSubtitle: false,
          drawComposer: false,
          drawPartNames: false,
          drawFromMeasureNumber: range.from,
          drawUpToMeasureNumber: range.to,
        });

        osmd.current = instance;
        await instance.load(xml);
        if (cancelled) return;

        instance.zoom = zoom;
        instance.render();
        setReady(true);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not render notation");
      }
    })();

    return () => {
      cancelled = true;
      try {
        osmd.current?.clear();
      } catch {
        /* disposing a half-initialised instance is not worth surfacing */
      }
      osmd.current = null;
      host.innerHTML = "";
    };
  }, [xml, fromMeasure, toMeasure, measureOffset, zoom]);

  // Re-render on width change so the score reflows instead of clipping.
  useEffect(() => {
    if (!container.current || !ready) return;
    const host = container.current;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        try {
          osmd.current?.render();
        } catch {
          /* mid-teardown */
        }
      });
    });
    observer.observe(host);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [ready]);

  if (error) {
    return (
      <div className="rounded-2xl border border-white/10 bg-zinc-800/40 p-4 text-xs text-zinc-500">
        Notation unavailable — {error}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10 bg-zinc-900/60 p-3">
      {!ready && <div className="h-24 animate-pulse rounded-xl bg-zinc-800/50" />}
      <div ref={container} className={ready ? "" : "hidden"} />
    </div>
  );
}
