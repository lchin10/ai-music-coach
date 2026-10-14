import type { Page } from "@playwright/test";

/** Everything that went wrong on a page while a test drove it. A screenshot
 *  can look right while the console is full of errors, so both are checked. */
export function watch(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") problems.push(`console: ${msg.text()}`);
  });
  page.on("pageerror", (err) => problems.push(`pageerror: ${err.message}`));
  page.on("response", (res) => {
    if (res.status() >= 400) problems.push(`${res.status()} ${res.request().method()} ${res.url()}`);
  });
  return problems;
}
