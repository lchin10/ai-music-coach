import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { AUTH_FILE, WEB, admin, anon, resetRuntime, seed, storageKey, testUser } from "./fixture";

/** Seed the test account and sign it in, without Google or an email inbox. */
export default async function globalSetup() {
  const db = admin();
  const user = await testUser(db);
  await seed(db, user.id);
  await resetRuntime(db, user.id);

  const { data, error } = await anon().auth.verifyOtp({
    token_hash: user.tokenHash,
    type: "magiclink",
  });
  if (error || !data.session) throw error ?? new Error("no session from magic link");

  mkdirSync(dirname(AUTH_FILE), { recursive: true });
  writeFileSync(
    AUTH_FILE,
    JSON.stringify({
      cookies: [],
      origins: [
        {
          origin: WEB,
          localStorage: [{ name: storageKey(), value: JSON.stringify(data.session) }],
        },
      ],
    })
  );
  process.env.E2E_USER_ID = user.id;
}
