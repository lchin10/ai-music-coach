/**
 * How a piece is named on screen.
 *
 * `pieces.title` is the upload filename and always will be — /retry re-fetches
 * the PDF by it. `work_title` and `composer` are the normalised names written
 * at processing time (backend/app/service/identify.py). Pieces processed
 * before that existed have neither, so everything falls back to a tidied
 * filename rather than showing a blank card.
 */

export type NamedPiece = {
  title: string;
  work_title?: string | null;
  composer?: string | null;
};

/** Mirrors identify.tidy_filename on the backend. */
export function tidyFilename(fileName: string): string {
  return (
    fileName
      .replace(/\.[^.]+$/, "")
      .replace(/^IMSLP\d+[-_]*/i, "")
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ")
      .trim() || fileName
  );
}

export function displayTitle(piece: NamedPiece): string {
  return piece.work_title?.trim() || tidyFilename(piece.title ?? "");
}

export function displayComposer(piece: NamedPiece): string {
  return piece.composer?.trim() ?? "";
}

/** Date only — the upload timestamp is noise on a piece card. */
export function uploadedOn(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}
