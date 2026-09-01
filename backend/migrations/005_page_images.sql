-- Show the real engraving instead of a re-render of the OMR output.
--
-- Audiveris drops detail on dense scores -- on the Rachmaninoff test piece it
-- kept 598 notes and 13 dynamics but zero fingerings, so rendering its
-- MusicXML showed music that did not match the page. The PDF is the ground
-- truth, so pages are rendered to PNG at processing time and shown directly.
--
-- [{page, start_measure, end_measure, path, bytes}], measure numbers in the
-- same scheme as sections.start_measure. Page breaks come from the MusicXML,
-- which records them reliably even when note recognition struggles.

alter table pieces
  add column if not exists page_images jsonb default '[]'::jsonb;

-- The rendered pages are PNGs, which 003's list did not cover.
update storage.buckets
set allowed_mime_types = allowed_mime_types || array['image/png', 'image/jpeg']
where id = 'pieces'
  and not (allowed_mime_types @> array['image/png']);
