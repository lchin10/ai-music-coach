import { expect, test, type Page } from "@playwright/test";
import { AUTH_FILE, PIECE_ID, admin, resetRuntime } from "./fixture";
import { watch } from "./watch";

async function snapshot(page: Page, path: string, name: string) {
  const problems = watch(page);
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  await expect(page).toHaveScreenshot(`${name}.png`, { fullPage: true });
  expect(problems).toEqual([]);
}

test.describe("signed out", () => {
  const pages: [string, string][] = [
    ["/", "home"],
    ["/signin", "signin"],
    ["/signup", "signup"],
    ["/profile", "profile"],
  ];
  for (const [path, name] of pages) {
    test(name, ({ page }) => snapshot(page, path, `signed-out-${name}`));
  }
});

test.describe("signed in", () => {
  test.use({ storageState: AUTH_FILE });
  // Same practice state every time, whatever ran before.
  test.beforeEach(() => resetRuntime(admin(), process.env.E2E_USER_ID!));

  const pages: [string, string][] = [
    ["/", "home"],
    ["/profile", "profile"],
    ["/upload", "upload"],
    ["/upload-confirmation", "upload-confirmation"],
    [`/piece/${PIECE_ID}`, "piece"],
    [`/practice/${PIECE_ID}`, "practice"],
  ];
  for (const [path, name] of pages) {
    test(name, ({ page }) => snapshot(page, path, `signed-in-${name}`));
  }
});
