import { admin, resetRuntime, testUser } from "./fixture";

/** Leave the test account as setup found it: piece seeded, no practice history. */
export default async function globalTeardown() {
  const db = admin();
  const user = await testUser(db);
  await resetRuntime(db, user.id);
}
