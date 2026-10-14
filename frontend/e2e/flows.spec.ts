import { expect, test } from "@playwright/test";
import { AUTH_FILE, PIECE_ID, admin, resetRuntime } from "./fixture";
import { watch } from "./watch";

const userId = () => process.env.E2E_USER_ID!;

test.describe("auth routing", () => {
  test.use({ storageState: AUTH_FILE });

  test("finished onboarding lands on home", async ({ page }) => {
    await page.goto("/return");
    await expect(page).toHaveURL(/\/$/);
  });

  test("unfinished onboarding is sent to onboarding", async ({ page }) => {
    const db = admin();
    await db.from("profiles").update({ onboarding_complete: false }).eq("id", userId());
    try {
      await page.goto("/return");
      await expect(page).toHaveURL(/\/onboarding$/);
    } finally {
      await db.from("profiles").update({ onboarding_complete: true }).eq("id", userId());
    }
  });

  test("a signed-in visit to sign-in goes home", async ({ page }) => {
    await page.goto("/signin");
    await expect(page).toHaveURL(/\/$/);
  });
});

test.describe("practice", () => {
  test.use({ storageState: AUTH_FILE });

  test("nailing a step advances, and leaving ends the session", async ({ page }) => {
    await resetRuntime(admin(), userId());
    const problems = watch(page);
    await page.goto(`/practice/${PIECE_ID}`);
    const nailed = page.getByRole("button", { name: /Nailed it/ });
    await expect(nailed).toBeVisible();

    const before = await page.locator("main").innerText();
    await nailed.click();
    await expect.poll(() => page.locator("main").innerText()).not.toBe(before);

    await page.getByRole("button", { name: "Back to piece" }).click();
    await expect(page).toHaveURL(new RegExp(`/piece/${PIECE_ID}$`));

    const db = admin();
    await expect
      .poll(async () => {
        const { data } = await db
          .from("practice_sessions")
          .select("ended_at")
          .eq("user_id", userId())
          .eq("piece_id", PIECE_ID);
        return (data ?? []).some((s) => s.ended_at !== null);
      })
      .toBe(true);

    const { data: attempts } = await db
      .from("step_attempts")
      .select("self_report")
      .eq("user_id", userId());
    expect(attempts).toEqual([{ self_report: "nailed" }]);
    expect(problems).toEqual([]);
  });
});

test.describe("upload", () => {
  test.use({ storageState: AUTH_FILE });

  test("a non-PDF is refused before anything is sent", async ({ page }) => {
    await page.goto("/upload");
    // The page uses alert(), which blocks until dismissed.
    const alerts: string[] = [];
    page.on("dialog", (d) => {
      alerts.push(d.message());
      d.dismiss();
    });
    await page.locator("#file-input").setInputFiles({
      name: "notes.txt",
      mimeType: "text/plain",
      buffer: Buffer.from("not music"),
    });
    await expect.poll(() => alerts).toEqual(["Please select a PDF file only."]);
    await expect(page.getByText("Drag & drop your PDF")).toBeVisible();
    await expect(page.getByRole("button", { name: "Upload & Analyze" })).toBeDisabled();
  });

  test("an oversized PDF is rejected by the detector and nothing is stored", async ({ page }) => {
    await page.goto("/upload");
    await page.locator("#file-input").setInputFiles({
      name: "huge.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.alloc(26 * 1024 * 1024, "%"),
    });
    await page.getByRole("button", { name: "Upload & Analyze" }).click();
    await expect(
      page.getByRole("main").getByText("That file is too large. Please upload a single piece.")
    ).toBeVisible();

    const { data } = await admin().from("pieces").select("id").eq("user_id", userId());
    expect(data).toEqual([{ id: PIECE_ID }]);
  });
});
