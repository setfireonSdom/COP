import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { checkDraftPublication, publishDraft } from "../lib/api";
import { hasPublicationWarnings, PublicationWarnings } from "../components/publication-warnings";

describe("publication findings", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows concept, stage, and missing-source findings without hiding the repair", () => {
    const findings = {
      concept_frame: [{ code: "CONCEPT_UNUSED", entity_ref: "concept.orphan", explanation: "No Stage uses it.", recommended_change: "Review bindings manually." }],
      content_gate: [{ code: "MISSING_STAGE_EXAMPLE", entity_ref: "stage.example", explanation: "No example.", recommended_change: "Add a concrete example." }],
      unresolved_evidence: [{ entity_ref: "stage.source", collection: "stages", source_id: "missing-source" }],
    };
    const html = renderToStaticMarkup(createElement(PublicationWarnings, { findings }));
    expect(hasPublicationWarnings(findings)).toBe(true);
    for (const text of ["concept.orphan", "Review bindings manually.", "stage.example", "missing-source", "do not verify factual accuracy"]) expect(html).toContain(text);
  });

  it("renders no warning for a clean response", () => {
    expect(hasPublicationWarnings({ content_gate: [], concept_frame: null })).toBe(false);
    expect(renderToStaticMarkup(createElement(PublicationWarnings, { findings: {} }))).toBe("");
  });

  it("preflights with GET and sends the reviewed revision with the explicit publish", async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ updated_at: "reviewed-time", concept_frame: [] }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await checkDraftPublication("draft/id");
    expect(fetch.mock.calls[0][0]).toContain("drafts/draft%2Fid/publish-check");
    expect(fetch.mock.calls[0][1].method ?? "GET").toBe("GET");
    await publishDraft("draft/id", "Reviewed changes", "reviewed-time");
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ change_summary: "Reviewed changes", reviewed_updated_at: "reviewed-time" });
  });
});
