import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { launch } = vi.hoisted(() => ({ launch: vi.fn() }));
vi.mock("@playwright/test", () => ({ chromium: { launch } }));

import { assertSafeChromeVersion, chromeLaunchOptions, compareVersions, launchChrome } from "../scripts/safe-browser.mjs";

describe("shared browser policy", () => {
  beforeEach(() => {
    vi.stubEnv("PLAYWRIGHT_CHANNEL", "chrome");
    launch.mockReset();
  });
  afterEach(() => vi.unstubAllEnvs());

  it.each(["chromium", "chromium-headless-shell", "chromium-tip-of-tree", "chrome-for-testing", "firefox", "unknown"])("refuses %s before launch", async (channel) => {
    vi.stubEnv("PLAYWRIGHT_CHANNEL", channel);
    await expect(launchChrome()).rejects.toThrow("Refusing Playwright channel");
    expect(launch).not.toHaveBeenCalled();
  });

  it.each(["unknown", "", "156.0.8078.4", "156.0.8078.73junk", "NaN.0.0.0"])("rejects and closes engine version %s before returning a browser", async (version) => {
    const close = vi.fn().mockResolvedValue(undefined);
    launch.mockResolvedValue({ version: () => version, close });
    await expect(launchChrome()).rejects.toThrow();
    expect(close).toHaveBeenCalledOnce();
  });

  it("never masks a version failure with a shutdown failure", async () => {
    launch.mockResolvedValue({ version: () => "unknown", close: vi.fn().mockRejectedValue(new Error("close failed")) });
    await expect(launchChrome()).rejects.toThrow("Chrome version must be known");
  });

  it("uses system Chrome and requests sandboxing in headless and headed runs", async () => {
    const browser = { version: () => "156.0.8078.80", close: vi.fn() };
    launch.mockResolvedValue(browser);
    expect(chromeLaunchOptions()).toEqual({ channel: "chrome", chromiumSandbox: true });
    expect(await launchChrome({ headless: false })).toBe(browser);
    expect(launch).toHaveBeenCalledWith({ channel: "chrome", chromiumSandbox: true, headless: false });
  });

  it("compares numeric versions rather than lexical strings", () => {
    expect(compareVersions("156.0.8078.4", "156.0.8078.73")).toBeLessThan(0);
    expect(compareVersions("156.0.8078.100", "156.0.8078.73")).toBeGreaterThan(0);
    expect(compareVersions("157.0", "156.0.8078.73")).toBeGreaterThan(0);
    expect(compareVersions("156.0.8078.73", "156.0.8078.73")).toBe(0);
    expect(() => assertSafeChromeVersion("unknown")).toThrow();
    expect(() => compareVersions("156abc", "156")).toThrow();
  });

  it("keeps E2E launch and CI preflight on the shared guard", () => {
    const fixture = readFileSync(new URL("../e2e/fixtures.ts", import.meta.url), "utf8");
    const config = readFileSync(new URL("../playwright.config.ts", import.meta.url), "utf8");
    const ci = readFileSync(new URL("../../../.github/workflows/ci.yml", import.meta.url), "utf8");
    expect(fixture).toContain("await launchChrome({ headless })");
    expect(config).toContain("chromeLaunchOptions()");
    expect(ci).toContain("node apps/web/scripts/check-browser-security.mjs");
    expect(ci).not.toMatch(/run:.*playwright install/);
  });
});
