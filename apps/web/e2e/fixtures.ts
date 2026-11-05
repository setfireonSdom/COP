import { expect, test as base, type Page } from "@playwright/test";
import { launchChrome } from "../scripts/safe-browser.mjs";

/**
 * A project with exactly one published version: the state a real user's project
 * is in after their first publish.
 *
 * The fixture goes through the same path a user takes, because the API has no
 * shortcut: start a run, wait for the candidate, make it the draft, publish it.
 * That also means the artifact is whatever the Mock Provider synthesizes, not a
 * hand-written fixture, so tests read the real ids and titles back from the API
 * instead of assuming them.
 *
 * It deliberately does not reuse the seeded reference project. A failing test
 * would otherwise leave the user's LangChain reference edited.
 */

export const test = base.extend({
  // Every browser-driven spec imports this fixture. Check the actual engine
  // before creating a context/page, not only a CLI version during CI setup.
  browser: async ({ headless }, provideBrowser) => {
    const browser = await launchChrome({ headless });
    try {
      await provideBrowser(browser);
    } finally {
      await browser.close();
    }
  },
});
export { expect };

export interface FirstGoal {
  id: string;
  title: string;
  outcome: string;
}

import { API_URL } from "./endpoints";

export { API_URL };

export interface VersionedProject {
  projectId: string;
  versionId: string;
  firstGoal: FirstGoal;
}

const TERMINAL = ["completed", "needs_attention", "failed", "cancelled"];
async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`POST ${path} failed with HTTP ${response.status}: ${await response.text()}`);
  }
  return (await response.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  return (await response.json()) as T;
}

/** Poll a run to a terminal state the way a client without SSE would. */
async function waitForRun(runId: string): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const run = await getJson<{ status: string }>(`/generation-runs/${runId}`);
    if (TERMINAL.includes(run.status)) return;
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`run ${runId} never reached a terminal state`);
}

export async function createVersionedProject(): Promise<VersionedProject> {
  const project = await postJson<{ id: string }>("/projects", {
    title: `E2E versioned ${Date.now()}`,
    domain: "E2E Versioned Domain",
    scope: "Version history verification",
  });

  const run = await postJson<{ id: string }>(`/projects/${project.id}/generation-runs`, {
    topic: "Draft lifecycle",
    mode: "fast",
  });
  await waitForRun(run.id);

  const draft = await postJson<{ id: string }>(
    `/projects/${project.id}/drafts/from-run/${run.id}`,
  );
  const version = await postJson<{ id: string; version_number: number }>(
    `/drafts/${draft.id}/publish`,
    { change_summary: "Seeded v1" },
  );

  const detail = await getVersion(version.id);
  const goal = detail.artifact.goals[0];
  if (!goal) throw new Error("the published artifact has no goals to edit");

  return { projectId: project.id, versionId: version.id, firstGoal: goal };
}

/* No draft cleanup helper: every test builds its own project, so one test
   cannot leave an active draft behind for the next one to trip over. */

export async function getDraft(projectId: string): Promise<{
  id: string;
  artifact: { goals: { id: string; title: string; outcome: string }[] };
} | null> {
  const response = await fetch(`${API_URL}/projects/${projectId}/draft`);
  if (response.status === 404) return null;
  return (await response.json()) as never;
}

export interface VersionSummary {
  id: string;
  version_number: number;
  parent_version_id: string | null;
  change_summary: string;
}

export async function getVersions(projectId: string): Promise<VersionSummary[]> {
  return getJson<VersionSummary[]>(`/projects/${projectId}/versions`);
}

export async function getVersion(versionId: string): Promise<{
  artifact: { goals: { id: string; title: string; outcome: string }[] };
}> {
  return getJson(`/versions/${versionId}`);
}

/**
 * Wait for the app to actually hydrate, not merely to render.
 *
 * The app ships a `loading.tsx` Suspense fallback, so a page can be fully
 * painted while its client components have not attached. Waiting on visible text
 * alone would therefore pass against a page where every button is dead, which is
 * exactly the failure this helper exists to catch.
 */
export async function waitForHydration(page: Page, selector: string): Promise<void> {
  await expect(page.locator(selector).first()).toBeVisible();
  await page.waitForFunction(
    (sel) => {
      const el = document.querySelector(sel);
      return !!el && Object.keys(el).some((key) => key.startsWith("__reactFiber"));
    },
    selector,
    { timeout: 15_000 },
  );
}
