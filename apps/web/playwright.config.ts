import { defineConfig, devices } from "@playwright/test";

import { API_URL, BASE_URL } from "./e2e/endpoints";
import { chromeLaunchOptions } from "./scripts/safe-browser.mjs";

const chrome = chromeLaunchOptions();

/**
 * E2E runs against the real Compose stack, not a mock.
 *
 * The behaviour worth protecting here cannot be observed in a unit test: it
 * lives in the interaction between the client component, the JSONB draft row,
 * and the validation the API re-runs on every write. A fake fetch would assert
 * only that the fake was called.
 *
 * The suite talks to a throwaway database seeded by `globalSetup`, for the same
 * reason `make test` does: these tests truncate tables, and pointing them at
 * the development database would delete real projects.
 *
 * Start the stack first (`POSTGRES_HOST_PORT=55432 docker compose up -d`), or
 * set E2E_BASE_URL when the app is already listening elsewhere.
 */
export default defineConfig({
  testDir: "./e2e",
  // Serial: every test shares one seeded project, and a parallel worker would
  // truncate another's fixture mid-assertion.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    channel: chrome.channel,
    launchOptions: { chromiumSandbox: chrome.chromiumSandbox },
  },
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  metadata: { apiUrl: API_URL },
});
