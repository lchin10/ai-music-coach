-- Phase 3 follow-up: let the `pieces` bucket hold MusicXML, not just PDFs.
--
-- The bucket was restricted to application/pdf, so storing the Audiveris .mxl
-- failed with a 415 regardless of the content type sent. .mxl is a zip
-- container, hence the zip/octet-stream entries; the xml types cover an
-- uncompressed .musicxml fallback.
--
-- The size limit was 5 MB while the API accepted 25 MB, so a large score
-- passed the router's check and then failed the upload. Raised to match
-- MAX_UPLOAD_BYTES in app/routers/sheet_music.py -- keep the two in step.

update storage.buckets
set
  allowed_mime_types = array[
    'application/pdf',
    'application/zip',
    'application/octet-stream',
    'application/xml',
    'text/xml',
    'application/vnd.recordare.musicxml',
    'application/vnd.recordare.musicxml+xml'
  ],
  file_size_limit = 26214400  -- 25 MB
where id = 'pieces';
