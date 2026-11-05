import type { Browser } from "@playwright/test";

export const MIN_SAFE_CHROMIUM: string;
export function chromeLaunchOptions(): { channel: string; chromiumSandbox: true };
export function assertSafeChromeVersion(version: string): void;
export function launchChrome(options?: { headless?: boolean }): Promise<Browser>;
export function compareVersions(a: string, b: string): number;
