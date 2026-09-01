-- Phase 3 follow-up: let users READ their own files.
--
-- storage.objects had policies for INSERT and DELETE but none for SELECT.
-- Uploading and deleting therefore worked while every download was denied,
-- and Supabase masks a denied read as "Object not found" rather than a
-- permission error — so the score looked missing when it was actually there.
--
-- This is the first feature that reads from storage; nothing had needed it
-- before. The condition mirrors the existing INSERT policy: a user may touch
-- only files under their own {user_id}/ folder.

create policy "Users can read their own files"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'pieces'
  and (auth.uid())::text = (storage.foldername(name))[1]
);
