/**
 * The e2e test user and its seeded piece.
 *
 * These tests run against the PRODUCTION Supabase project. Everything they
 * write belongs to one dedicated account, and every write or delete is
 * filtered by that account's id. `testUserId()` refuses to return an id for
 * any other email, so a wrong lookup fails the run instead of touching real data.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export const E2E_EMAIL = "e2e-test@ai-music-coach.invalid";
export const WEB = "http://localhost:3100";
export const API = "http://localhost:8100";
export const AUTH_FILE = "e2e/.auth/user.json";

export const PIECE_ID = "e2e00000-0000-4000-8000-000000000001";
export const PLAN_ID = "e2e00000-0000-4000-8000-000000000002";
export const SECTION_IDS = [
  "e2e00000-0000-4000-8000-000000000011",
  "e2e00000-0000-4000-8000-000000000012",
];

function env(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not set (expected in frontend/ or backend/ .env.local)`);
  return value;
}

export function admin(): SupabaseClient {
  return createClient(env("NEXT_PUBLIC_SUPABASE_URL"), env("SUPABASE_SERVICE_ROLE_KEY"), {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

export function anon(): SupabaseClient {
  return createClient(env("NEXT_PUBLIC_SUPABASE_URL"), env("NEXT_PUBLIC_SUPABASE_ANON_KEY"), {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

/** The key supabase-js keeps the browser session under. */
export function storageKey(): string {
  return `sb-${new URL(env("NEXT_PUBLIC_SUPABASE_URL")).hostname.split(".")[0]}-auth-token`;
}

/** The test account's id, plus a one-time token to sign in as it. */
export async function testUser(db: SupabaseClient) {
  const created = await db.auth.admin.createUser({ email: E2E_EMAIL, email_confirm: true });
  if (created.error && created.error.code !== "email_exists") throw created.error;

  const link = await db.auth.admin.generateLink({ type: "magiclink", email: E2E_EMAIL });
  if (link.error) throw link.error;
  if (link.data.user.email !== E2E_EMAIL) {
    throw new Error(`refusing to continue: resolved ${link.data.user.email}, not ${E2E_EMAIL}`);
  }
  return { id: link.data.user.id, tokenHash: link.data.properties.hashed_token };
}

/** Undo everything a test run can write. Scoped to the test user throughout. */
export async function resetRuntime(db: SupabaseClient, userId: string) {
  const steps = [
    db.from("practice_sessions").delete().eq("user_id", userId), // cascades step_attempts
    db.from("section_mastery").delete().eq("user_id", userId),
    db.from("plan_steps").delete().eq("plan_id", PLAN_ID).neq("source", "plan"),
    db.from("profiles").update({ onboarding_complete: true }).eq("id", userId),
  ];
  for (const step of steps) {
    const { error } = await step;
    if (error) throw error;
  }
}

function section(id: string, start: number, end: number) {
  return {
    id,
    piece_id: PIECE_ID,
    title: `Section ${start === 1 ? "A" : "B"}`,
    start_measure: start,
    end_measure: end,
    difficulty: 45,
    notes: "Seeded by the e2e suite.",
    analysis_data: {
      difficulty: 45,
      key_challenges: ["even sixteenths"],
      techniques: ["scales"],
      musical_character: "bright",
      risk_measures: [start + 2],
      tempo_floor: 60,
      tempo_target: 96,
    },
  };
}

/** A ready piece with two sections and a plan, without running Audiveris. */
export async function seed(db: SupabaseClient, userId: string) {
  const existing = await db.from("pieces").select("user_id").eq("id", PIECE_ID).maybeSingle();
  if (existing.data && existing.data.user_id !== userId) {
    throw new Error(`refusing to continue: piece ${PIECE_ID} belongs to someone else`);
  }

  const writes = [
    db.from("profiles").upsert({
      id: userId,
      name: "E2E Test",
      piano_level: "intermediate",
      years_experience: 3,
      onboarding_complete: true,
    }),
    db.from("pieces").upsert({
      id: PIECE_ID,
      user_id: userId,
      title: "e2e-etude.pdf",
      work_title: "Etude in C major",
      composer: "E2E Composer",
      file_path: `${userId}/e2e-etude.pdf`,
      status: "ready",
      page_images: [],
      plan_quality: "full",
      created_at: "2026-01-01T00:00:00",
    }),
  ];
  for (const write of writes) {
    const { error } = await write;
    if (error) throw error;
  }

  const rest = [
    db.from("sections").upsert([section(SECTION_IDS[0], 1, 8), section(SECTION_IDS[1], 9, 16)]),
    db.from("practice_plans").upsert({ id: PLAN_ID, piece_id: PIECE_ID, version: 1 }),
  ];
  for (const write of rest) {
    const { error } = await write;
    if (error) throw error;
  }

  const { error } = await db.from("plan_steps").upsert(
    SECTION_IDS.map((sectionId, i) => ({
      id: `e2e00000-0000-4000-8000-00000000002${i}`,
      plan_id: PLAN_ID,
      section_id: sectionId,
      order_index: i,
      title: `Hands separate, section ${i === 0 ? "A" : "B"}`,
      description: "Each hand alone, slowly, until the notes are secure.",
      target_tempo: 60,
      drill_type: "hands_separate",
      focus_start_measure: i === 0 ? 1 : 9,
      focus_end_measure: i === 0 ? 8 : 16,
      source: "plan",
    }))
  );
  if (error) throw error;
}
