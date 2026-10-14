import { supabase } from "@/lib/supabaseClient";

export const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

/** `fetch` against the FastAPI backend as the signed-in user. The backend takes
 *  identity from this token alone, never from a user_id in the request. */
export async function backendFetch(path: string, init: RequestInit = {}) {
  const { data } = await supabase.auth.getSession();
  const headers = new Headers(init.headers);
  if (data.session) headers.set("Authorization", `Bearer ${data.session.access_token}`);
  return fetch(`${BACKEND_URL}${path}`, { ...init, headers });
}
