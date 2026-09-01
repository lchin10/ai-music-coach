/**
 * The ONLY place measure numbers are converted for rendering.
 *
 * Three numbering schemes are in play:
 *   1. The score's printed numbers — what the student reads. A piece opening
 *      with a pickup starts at 0.
 *   2. Ours — `sections.start_measure` / `plan_steps.focus_start_measure`.
 *      The backend keeps the score's numbers when they are usable and
 *      renumbers 1..N when Audiveris produced junk (see features.py).
 *   3. OSMD's `drawFromMeasureNumber` — its own 1-based count over the
 *      measures in the file.
 *
 * `pieces.measure_offset` records where our numbering starts, so scheme 2
 * maps onto scheme 3. Getting this wrong renders the wrong bars while
 * looking entirely plausible, so it lives in one function with one test.
 */
export function toOsmdMeasure(ourMeasure: number, offset: number): number {
  return ourMeasure - offset + 1;
}

/** Inclusive OSMD range for one of our measure ranges, clamped to >= 1. */
export function toOsmdRange(
  from: number,
  to: number,
  offset: number
): { from: number; to: number } {
  return {
    from: Math.max(1, toOsmdMeasure(from, offset)),
    to: Math.max(1, toOsmdMeasure(to, offset)),
  };
}
