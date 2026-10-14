import { defineConfig, devices } from "@playwright/test";
import { API, WEB } from "./e2e/fixture";

// Keys are read at runtime only. The service-role key lives in the backend's
// env; it stays in this Node process and is never handed to the browser.
for (const file of [".env.local", "../backend/.env.local"]) {
  try {
    process.loadEnvFile(file);
  } catch {}
}

export default defineConfig({
  testDir: "e2e",
  outputDir: "../test-logs/e2e-latest",
  snapshotPathTemplate: "e2e/__screenshots__/{testFileName}/{arg}-{projectName}{ext}",
  // One shared test account on production: no parallel writers.
  workers: 1,
  fullyParallel: false,
  retries: 0,
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  reporter: [["list"], ["html", { outputFolder: "../test-logs/e2e-report", open: "never" }]],
  expect: {
    toHaveScreenshot: { maxDiffPixels: 0, animations: "disabled", stylePath: "e2e/screenshot.css" },
  },
  use: { baseURL: WEB, screenshot: "on", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
    // Flows mutate the shared test account, so they run once, on desktop.
    { name: "phone", use: { ...devices["Pixel 7"] }, testMatch: /pages\.spec/ },
  ],
  // Own ports, so a dev server you already have open is never reused with the
  // wrong backend URL.
  webServer: [
    {
      command: "python -m uvicorn app.main:app --port 8100 --env-file .env.local",
      cwd: "../backend",
      url: `${API}/`,
      env: { FRONTEND_DEV_URL: WEB },
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: "npx next dev -p 3100",
      url: WEB,
      env: { NEXT_PUBLIC_BACKEND_URL: API },
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
