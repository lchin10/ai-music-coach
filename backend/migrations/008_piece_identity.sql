-- Name the piece properly.
--
-- `pieces.title` has always been the upload filename, so every screen showed
-- "IMSLP11125-Godowsky_APS_47_Rachmaninoff-Prelude_Op.3_No.2.pdf". Audiveris
-- OCRs the title block but on a scan produces things like
-- "S. RACHMANINOFF, 0p. 3. Na. 2", so these are normalised at processing time
-- (app/service/identify.py) rather than trusted raw.
--
-- title stays as it is: it's the filename, and it's what /retry re-downloads by.

alter table pieces
  add column if not exists work_title text,
  add column if not exists composer   text;
