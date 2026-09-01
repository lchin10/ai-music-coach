"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabaseClient";

/**
 * Fetch a piece's MusicXML once, for every <Score> on the page to share.
 *
 * Fetching per section instead would pull the same file N times over the
 * network for no benefit.
 */
export default function useScoreXml(musicxmlPath: string | null | undefined) {
  const [xml, setXml] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!musicxmlPath) return;

    let cancelled = false;

    (async () => {
      const { data, error: dlError } = await supabase.storage
        .from("pieces")
        .download(musicxmlPath);

      if (cancelled) return;
      if (dlError || !data) {
        setError(dlError?.message ?? "Could not load the score");
        return;
      }
      setXml(data);
    })();

    return () => {
      cancelled = true;
    };
  }, [musicxmlPath]);

  return { xml, error };
}
