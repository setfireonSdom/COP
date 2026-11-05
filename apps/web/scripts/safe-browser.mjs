/**
 * A guarded Playwright launcher for every local and CI browser check.
 *
 * Why this exists
 * ---------------
 * `@playwright/test@1.64.1` pins Chromium 156.0.8078.4, which predates the
 * 156.0.8078.73 fix for CVE-2026-118306/118331/118344/118348 (arbitrary code
 * execution from a crafted HTML page). Playwright also leaves the Chromium
 * sandbox off by default (`chromiumSandbox` -> `false`), so a compromised
 * renderer is not contained.
 *
 * Instead of removing browser verification entirely, this module refuses the
 * bundled engine and requires a locally installed branded Chrome, with the
 * sandbox explicitly on. That keeps the regression suite meaningful while
 * removing the vulnerable binary from the trust path.
 *
 * What this does NOT do: it cannot make an old system Chrome safe. It only
 * guarantees we never silently fall back to Playwright's pinned build.
 */
import assert from "node:assert/strict";
import { chromium } from "@playwright/test";

/** Fix boundary for the four Chromium advisories, not a general safety guarantee. */
export const MIN_SAFE_CHROMIUM = "156.0.8078.73";

const SYSTEM_CHROME_CHANNELS = new Set(["chrome", "chrome-beta", "chrome-dev", "chrome-canary"]);

/** Shared by scripts and the E2E runner. Never accept arbitrary launch flags. */
export function chromeLaunchOptions() {
  const channel = process.env.PLAYWRIGHT_CHANNEL || "chrome";
  assert.ok(
    SYSTEM_CHROME_CHANNELS.has(channel),
    `Refusing Playwright channel '${channel}': only installed system Chrome channels are allowed.`,
  );
  return { channel, chromiumSandbox: true };
}

export function assertSafeChromeVersion(version) {
  assert.match(version, /^\d+\.\d+\.\d+\.\d+$/, "Chrome version must be known and numeric.");
  assert.ok(
    compareVersions(version, MIN_SAFE_CHROMIUM) >= 0,
    `Chrome ${version} is older than ${MIN_SAFE_CHROMIUM}; update Chrome before running browser checks.`,
  );
}

export async function launchChrome({ headless = true } = {}) {
  const browser = await chromium.launch({
    ...chromeLaunchOptions(),
    headless,
  });
  try {
    assertSafeChromeVersion(browser.version());
  } catch (error) {
    // No page has been created. Do not leave a rejected browser running, and
    // preserve the original version error if shutdown also fails.
    await browser.close().catch(() => {});
    throw error;
  }
  return browser;
}

/** Numeric dotted-version comparison; avoids a semver dependency. */
export function compareVersions(a, b) {
  const parse = (value) => {
    assert.match(value, /^\d+(?:\.\d+){0,3}$/, "Expected a numeric dotted version.");
    const parts = value.split(".").map(Number);
    assert.ok(parts.every(Number.isSafeInteger), "Version components must be safe integers.");
    return parts;
  };
  const pa = parse(a);
  const pb = parse(b);
  for (let index = 0; index < Math.max(pa.length, pb.length); index += 1) {
    const diff = (pa[index] ?? 0) - (pb[index] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}
