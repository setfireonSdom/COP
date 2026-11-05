import type { Page } from "@playwright/test";

import {
  API_URL,
  createVersionedProject,
  expect,
  getDraft,
  getVersion,
  getVersions,
  test,
  waitForHydration,
  type VersionedProject,
} from "./fixtures";

/**
 * The M5 draft loop, driven through a real browser.
 *
 * These cover the acceptance criteria from `23-coding-agent-milestones.md`: a
 * published version cannot be changed, user edits survive a refresh, and v2
 * records parent v1. None of it was verifiable before this file existed. Unit
 * tests and SSR HTML cannot tell you whether a button is wired to its handler,
 * and they cannot see a rejected save that silently discards what the user typed.
 */
test.describe("draft lifecycle", () => {
  /**
   * Soft-delete whatever a test created.
   *
   * These tests run against the development stack, so without this they would
   * leave one project per test in the user's library, and a soft-deleted
   * project is excluded from the project list.
   */
  const created: string[] = [];

  test.afterEach(async () => {
    await Promise.all(
      created.splice(0).map((id) =>
        fetch(`${API_URL}/projects/${id}`, { method: "DELETE" }).catch(() => undefined),
      ),
    );
  });

  async function versioned(): Promise<VersionedProject> {
    const project = await createVersionedProject();
    created.push(project.projectId);
    return project;
  }

  /**
   * Fork v1 into a draft and land on the draft overview.
   *
   * The wait is a document load, not a client-side transition, so
   * `waitUntil: "load"` is the honest setting here.
   */
  async function openDraft(page: Page, projectId: string) {
    await page.goto(`/projects/${projectId}/versions`);
    await waitForHydration(page, ".version-actions");
    await page.getByRole("button", { name: /Draft from v1/i }).click();
    await page.waitForURL(`**/draft`, { waitUntil: "load" });
    await waitForHydration(page, ".draft-toolbar");
  }

  /** Open one goal's editor and return its locators. */
  async function openGoalEditor(page: Page, project: VersionedProject) {
    await page.goto(`/projects/${project.projectId}/draft`);
    await waitForHydration(page, ".draft-toolbar");
    await page.locator(".draft-advanced > summary").click();
    await page
      .locator(".draft-entity-list a", { hasText: project.firstGoal.title })
      .first()
      .click();
    await page.waitForURL(`**/draft/goals/**`, { waitUntil: "load" });
    await waitForHydration(page, ".draft-editor");
    return {
      title: page.locator(".draft-field", { hasText: "Title" }).locator("input"),
      outcome: page.locator(".draft-field", { hasText: "Outcome" }).locator("textarea"),
    };
  }

  test("a version can be forked into a draft and edited in the browser", async ({
    page,
  }) => {
    const project = await versioned();
    await openDraft(page, project.projectId);
    await expect(page.getByRole("heading", { name: "Your learning path", exact: true })).toBeVisible();

    const { outcome } = await openGoalEditor(page, project);
    await outcome.fill("Edited outcome that must survive a reload.");

    // Save stays disabled until something actually changes, then enables.
    const save = page.getByRole("button", { name: /Save to draft/i });
    await expect(save).toBeEnabled();
    await expect(page.locator(".draft-dirty")).toContainText("unsaved change");

    await save.click();
    await expect(page.locator(".draft-saved")).toBeVisible();

    const draft = (await getDraft(project.projectId)) as {
      artifact: { goals: { id: string; outcome: string }[] };
    };
    const edited = draft.artifact.goals.find((goal) => goal.id === project.firstGoal.id);
    expect(edited?.outcome).toBe("Edited outcome that must survive a reload.");

    // The published version is untouched by a draft edit.
    const v1 = await getVersion(project.versionId);
    const original = v1.artifact.goals.find((goal) => goal.id === project.firstGoal.id);
    expect(original?.outcome).toBe(project.firstGoal.outcome);
  });

  test("an edit survives a full page reload", async ({ page }) => {
    const project = await versioned();
    await openDraft(page, project.projectId);

    const { outcome } = await openGoalEditor(page, project);
    await outcome.fill("Persisted across a reload.");
    await page.getByRole("button", { name: /Save to draft/i }).click();
    await expect(page.locator(".draft-saved")).toBeVisible();

    // Reload the whole document, not a client-side navigation, so this proves
    // the value came from the database rather than from React state.
    await page.reload();
    await waitForHydration(page, ".draft-editor");
    await expect(
      page.locator(".draft-field", { hasText: "Outcome" }).locator("textarea"),
    ).toHaveValue("Persisted across a reload.");
  });

  test("publishing creates v2 that records v1 as its parent", async ({ page }) => {
    const project = await versioned();
    await openDraft(page, project.projectId);

    // Publishing is two-step. The confirm panel must appear before anything
    // irreversible happens, and v1 must still be the only version at that point.
    await page.getByRole("button", { name: /^Publish draft$/i }).click();
    await expect(page.locator(".draft-confirm")).toBeVisible();
    expect((await getVersions(project.projectId)).length).toBe(1);

    await page.locator(".draft-confirm input").fill("Clarified the draft lifecycle goal");
    await page.getByRole("button", { name: /^(Confirm publish|Publish with warnings)$/i }).click();

    await expect
      .poll(async () => (await getVersions(project.projectId)).length, { timeout: 15_000 })
      .toBe(2);

    const versions = await getVersions(project.projectId);
    const v2 = versions.find((item) => item.version_number === 2);
    expect(v2?.parent_version_id).toBe(project.versionId);
    expect(v2?.change_summary).toBe("Clarified the draft lifecycle goal");
    expect(versions.find((item) => item.version_number === 1)?.parent_version_id).toBeNull();

    // The draft is consumed, so the project is not left with an active draft
    // shadowing the version it just produced.
    expect(await getDraft(project.projectId)).toBeNull();
  });

  test("a published version cannot be changed by later draft work", async ({ page }) => {
    const project = await versioned();
    const before = await getVersion(project.versionId);

    await openDraft(page, project.projectId);
    const { outcome } = await openGoalEditor(page, project);
    await outcome.fill("A divergence that must not touch v1.");
    await page.getByRole("button", { name: /Save to draft/i }).click();
    await expect(page.locator(".draft-saved")).toBeVisible();

    await page.goto(`/projects/${project.projectId}/draft`);
    await waitForHydration(page, ".draft-toolbar");
    await page.getByRole("button", { name: /^Publish draft$/i }).click();
    await page.getByRole("button", { name: /^(Confirm publish|Publish with warnings)$/i }).click();
    await expect
      .poll(async () => (await getVersions(project.projectId)).length, { timeout: 15_000 })
      .toBe(2);

    const after = await getVersion(project.versionId);
    const goal = after.artifact.goals.find((item) => item.id === project.firstGoal.id);
    const original = before.artifact.goals.find((item) => item.id === project.firstGoal.id);
    expect(goal?.outcome).toBe(original?.outcome);
  });

  test("a rejected edit keeps the text the user typed", async ({ page }) => {
    const project = await versioned();
    await openDraft(page, project.projectId);
    const { title, outcome } = await openGoalEditor(page, project);

    // Emptying a required field is rejected by the API. Losing the surrounding
    // paragraph because one field was invalid is the worst possible outcome.
    await title.fill("Edited title");
    await outcome.fill("");
    await page.getByRole("button", { name: /Save to draft/i }).click();

    await expect(page.locator(".form-error")).toBeVisible();
    await expect(title).toHaveValue("Edited title");
    await expect(outcome).toHaveValue("");
  });

  test("discarding a draft requires confirmation and leaves v1 alone", async ({
    page,
  }) => {
    const project = await versioned();
    const before = await getVersion(project.versionId);

    await openDraft(page, project.projectId);
    await page.locator(".draft-more-actions > summary").click();
    await page.getByRole("button", { name: /Discard draft/i }).click();
    await expect(page.locator(".draft-confirm")).toBeVisible();
    // Nothing is gone yet.
    expect(await getDraft(project.projectId)).not.toBeNull();

    await page.getByRole("button", { name: /Discard the draft/i }).click();
    await expect
      .poll(async () => (await getDraft(project.projectId)) === null, { timeout: 15_000 })
      .toBe(true);

    expect(await getVersion(project.versionId)).toEqual(before);
    expect((await getVersions(project.projectId)).length).toBe(1);
  });

  test("only one draft can exist per project, and the UI says so", async ({ page }) => {
    const project = await versioned();
    await openDraft(page, project.projectId);

    // The single-draft rule is surfaced before the user can provoke a 409.
    await page.goto(`/projects/${project.projectId}/versions`);
    await waitForHydration(page, ".version-actions");
    await expect(page.getByRole("link", { name: /Open the active draft/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Draft from v1/i })).toHaveCount(0);
  });

  test("the draft overview pluralises section headings correctly", async ({ page }) => {
    const project = await versioned();
    await openDraft(page, project.projectId);

    // Guards the "5 main processs" bug, which no unit test or SSR check caught:
    // "Main Process" is the one label that does not pluralize by appending "s".
    const headings = await page.locator(".draft-section h2").allTextContents();
    expect(headings.length).toBeGreaterThan(0);
    for (const heading of headings) {
      expect(heading).not.toMatch(/ss\b/);
    }
    expect(headings.join(" ")).toMatch(/\d+ main processes?/);
  });
});
