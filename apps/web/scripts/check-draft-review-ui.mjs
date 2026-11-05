// Isolated interaction regression. Writes are intercepted; no live data is touched.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { launchChrome } from "./safe-browser.mjs";

const require = createRequire(import.meta.url);
const vitestRequire = createRequire(require.resolve("vitest/package.json"));
const { build } = createRequire(vitestRequire.resolve("vite"))("esbuild");
const result = await build({
  stdin: {
    contents: `import React from 'react';
      import { createRoot } from 'react-dom/client';
      import artifact from '../../fixtures/reference-langchain-cop.json';
      import { DraftReview } from './components/draft-review';
      import { DraftToolbar } from './components/draft-toolbar';
      createRoot(document.getElementById('root')).render(<>
        <header className="draft-page-header"><p className="eyebrow">REVIEW BEFORE YOU PUBLISH</p><h1>A personal learning path</h1><p>Review the route. Edit if needed, then publish to begin learning.</p></header>
        <DraftToolbar projectId="p" draftId="d" hasPublishedVersion={false} counts={{goals:5,processes:5,stages:22,concepts:16,operations:12,practices:5,shared_foundations:1}} />
        <DraftReview artifact={artifact} projectId="p" />
      </>);`,
    resolveDir: fileURLToPath(new URL("../", import.meta.url)), loader: "tsx",
  },
  bundle: true, write: false, outdir: "/virtual", format: "iife", jsx: "automatic",
  define: { "process.env.NODE_ENV": '"test"', "process.env.NEXT_PUBLIC_API_BASE_URL": '"/api/v1"', "process.env.INTERNAL_API_BASE_URL": "undefined" },
  plugins: [{ name: "isolated-links", setup(builder) {
    builder.onResolve({ filter: /^next\/link$/ }, () => ({ path: "link", namespace: "fixture" }));
    builder.onLoad({ filter: /.*/, namespace: "fixture" }, () => ({
      contents: "import React from 'react'; export default function Link(props) { return React.createElement('a',props,props.children); }", loader: "js", resolveDir: fileURLToPath(new URL("../", import.meta.url)),
    }));
  } }],
});
const css = await readFile(new URL("../app/globals.css", import.meta.url), "utf8") + result.outputFiles.filter((file) => file.path.endsWith(".css")).map((file) => file.text).join("\n");
const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>${css}</style></head><body><main class="content-wrap draft-review-page"><div id="root"></div></main><script>${result.outputFiles.find((file) => file.path.endsWith(".js")).text}</script></body></html>`;
const browser = await launchChrome();
try {
  const page = await browser.newPage();
  const errors = [];
  let publishes = 0;
  let discards = 0;
  let previewFails = false;
  let warn = false;
  let stale = false;
  let revision = "2026-11-03T00:00:00Z";
  const warnings = () => ({
    content_gate: [],
    concept_frame: warn ? [{ code: "CONCEPT_UNUSED", entity_ref: "concept.orphan", explanation: "No Stage uses this Concept.", recommended_change: "Review the bindings manually; text repair cannot change them." }] : [],
    unresolved_evidence: [],
  });
  page.on("pageerror", (e) => errors.push(e.message));
  await page.route("http://draft.test/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/") return route.fulfill({ contentType: "text/html", body: html });
    if (path === "/projects/p") return route.fulfill({ contentType: "text/html", body: "<h1>Project workspace</h1>" });
    if (path === "/api/v1/drafts/d/publish-check") {
      assert.equal(route.request().method(), "GET");
      if (previewFails) return route.fulfill({ status: 503, json: { error: { message: "Checks unavailable" } } });
      return route.fulfill({ json: { updated_at: revision, ...warnings() } });
    }
    if (path === "/api/v1/drafts/d/publish") {
      publishes++;
      assert.equal(route.request().postDataJSON().reviewed_updated_at, revision);
      if (stale) {
        stale = false;
        revision = "2026-11-03T00:01:00Z";
        return route.fulfill({ status: 409, json: { error: { code: "DRAFT_CHANGED", message: "The draft changed after review." } } });
      }
      return route.fulfill({ json: { id: "v1", ...warnings() } });
    }
    if (path === "/api/v1/drafts/d" && route.request().method() === "DELETE") { discards++; return route.fulfill({ status: 204 }); }
    throw new Error(`Unexpected request ${path}`);
  });
  await page.goto("http://draft.test/");
  await page.getByRole("heading", { name: "Your learning path", exact: true }).waitFor();
  await page.locator(".draft-review-goal[open] .draft-review-stage > summary").first().click();
  await page.locator(".draft-review-stage[open] .detail-item").first().waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "open stage must fit mobile width");
  await page.getByRole("button", { name: "Publish draft", exact: true }).click();
  await page.getByRole("button", { name: "Confirm publish", exact: true }).waitFor();
  assert.equal(publishes, 0, "opening a confirmation must not publish");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.locator(".draft-more-actions > summary").click();
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  await page.getByRole("button", { name: "Keep editing", exact: true }).waitFor();
  assert.equal(discards, 0, "opening a confirmation must not discard");
  await page.getByRole("button", { name: "Keep editing", exact: true }).click();
  await page.getByRole("button", { name: "Publish draft", exact: true }).click();
  await page.getByRole("button", { name: "Confirm publish", exact: true }).click();
  await page.waitForURL("http://draft.test/projects/p");
  assert.equal(publishes, 1);
  await page.goto("http://draft.test/");
  await page.locator(".draft-more-actions > summary").click();
  await page.getByRole("button", { name: "Discard draft", exact: true }).click();
  await page.getByRole("button", { name: "Discard the draft", exact: true }).click();
  await page.waitForURL("http://draft.test/projects/p");
  assert.equal(discards, 1);

  // Failed checks cannot enable publishing. Retry must be explicit and read-only.
  warn = true;
  previewFails = true;
  await page.goto("http://draft.test/");
  await page.getByRole("button", { name: "Publish draft", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "Checks unavailable" }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Confirm publish", exact: true }).isEnabled(), false);
  assert.equal(publishes, 1);
  previewFails = false;
  await page.getByRole("button", { name: "Check again", exact: true }).click();
  await page.getByRole("region", { name: "Publication warnings" }).waitFor();
  for (const width of [390, 1280]) for (const colorScheme of ["light", "dark"]) {
    await page.setViewportSize({ width, height: 844 });
    await page.emulateMedia({ colorScheme });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "warnings must fit both themes and widths");
  }
  stale = true;
  await page.getByRole("button", { name: "Publish with warnings", exact: true }).click();
  await page.getByRole("alert").filter({ hasText: "draft changed" }).waitFor();
  assert.equal(await page.getByRole("button", { name: "Confirm publish", exact: true }).isEnabled(), false);
  await page.getByRole("button", { name: "Check again", exact: true }).click();
  await page.getByRole("button", { name: "Publish with warnings", exact: true }).click();
  await page.getByRole("heading", { name: "Published with warnings", exact: true }).waitFor();
  assert.equal(page.url(), "http://draft.test/", "publication receipt must not be lost on redirect");
  assert.equal(await page.getByRole("button", { name: "Publish draft", exact: true }).count(), 0);
  assert.equal(publishes, 3);
  await page.getByRole("link", { name: "Open project", exact: true }).click();
  await page.waitForURL("http://draft.test/projects/p");
  assert.deepEqual(errors, []);
  console.log("Browser PASS: read-only preflight, visible warnings, fail-closed checks, stale-review rejection/retry, publication receipt, two widths × two themes, mock-only writes.");
} finally { await browser.close(); }
