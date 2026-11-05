"use client";

import { useState } from "react";

import { ApiError, checkDraftPublication, discardDraft, publishDraft } from "../lib/api";
import type { DraftCounts, PublishCheck, PublishResult } from "../lib/api";
import { hasPublicationWarnings, PublicationWarnings } from "./publication-warnings";

interface DraftToolbarProps {
  projectId: string;
  draftId: string;
  counts: DraftCounts;
  hasPublishedVersion: boolean;
}

/**
 * Publish or discard the active draft.
 *
 * Publishing is deliberately a two-step confirm with an optional summary: it is
 * the one action in the product that permanently freezes content, and the spec
 * requires it to be an explicit user decision. Discarding asks for a second
 * click too, because the draft may hold edits that were never published.
 */
export function DraftToolbar({ projectId, draftId, counts, hasPublishedVersion }: DraftToolbarProps) {
  const [mode, setMode] = useState<"idle" | "publish" | "discard">("idle");
  const [summary, setSummary] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [check, setCheck] = useState<PublishCheck | null>(null);
  const [published, setPublished] = useState<PublishResult | null>(null);

  async function reviewPublication() {
    setMode("publish");
    setPending(true);
    setError(null);
    setCheck(null);
    try {
      setCheck(await checkDraftPublication(draftId));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Publication checks could not be completed. Try again.");
    } finally {
      setPending(false);
    }
  }

  async function run(action: "publish" | "discard") {
    if (action === "publish" && !check) return;
    setPending(true);
    setError(null);
    try {
      if (action === "publish") {
        const result = await publishDraft(draftId, summary, check!.updated_at);
        if (hasPublicationWarnings(result)) {
          // Publishing succeeded. Keep the receipt visible and remove all
          // draft actions, so an unexpected warning is not lost on navigation.
          setPublished(result);
          return;
        }
      } else {
        await discardDraft(draftId);
      }
      // The draft no longer exists after publish/discard. Reload its project,
      // not the disappearing draft route (which would turn success into a 404).
      window.location.assign(`/projects/${projectId}`);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) setCheck(null);
      setError(cause instanceof ApiError ? cause.message : "That action could not be completed.");
    } finally {
      setPending(false);
    }
  }

  if (published) return (
    <section className="draft-toolbar" aria-label="Publication receipt" role="status">
      <h2>Published with warnings</h2>
      <PublicationWarnings findings={published} published />
      <a className="primary-button" href={`/projects/${projectId}`}>Open project</a>
    </section>
  );

  return (
    <section className="draft-toolbar" id="draft-actions" aria-label="Draft actions">
      <div className="draft-toolbar-head">
        <div>
          <p className="draft-toolbar-status"><span /> Unpublished draft</p>
          <p className="draft-toolbar-counts">{counts.goals} goals <span>·</span> {counts.stages} steps <span>·</span> {counts.practices} practices</p>
        </div>
        <div className="draft-toolbar-buttons">
          <button
            className="primary-button"
            disabled={pending}
            onClick={() => void reviewPublication()}
            type="button"
          >
            Publish draft
          </button>
          <details className="draft-more-actions">
            <summary>More</summary>
            <button
              className="draft-discard-button"
              disabled={pending}
              onClick={() => {
                setMode("discard");
                setError(null);
              }}
              type="button"
            >
              Discard draft
            </button>
          </details>
        </div>
      </div>

      {mode === "publish" && (
        <div className="draft-confirm">
          {check && <PublicationWarnings findings={check} />}
          {!check && pending && <p role="status">Checking this draft…</p>}
          <label className="draft-field">
            <span>
              What changed in this version<em>optional</em>
            </span>
            <input
              onChange={(event) => setSummary(event.target.value)}
              placeholder="Optional note about this version"
              type="text"
              value={summary}
            />
          </label>
          <p className="draft-confirm-note">
            Save this draft as a version in your workspace, then open Learn mode to follow the steps.
            This does not share anything publicly. {hasPublishedVersion && "Your current published version stays unchanged."}
          </p>
          <div className="draft-actions">
            <button className="primary-button" disabled={pending || !check} onClick={() => void run("publish")} type="button">
              {pending ? "Please wait…" : check && hasPublicationWarnings(check) ? "Publish with warnings" : "Confirm publish"}
            </button>
            {!check && !pending && <button className="secondary-button" onClick={() => void reviewPublication()} type="button">Check again</button>}
            <button className="secondary-button" disabled={pending} onClick={() => setMode("idle")} type="button">
              Cancel
            </button>
          </div>
        </div>
      )}

      {mode === "discard" && (
        <div className="draft-confirm">
          <p className="draft-confirm-note">
            Discarding throws the draft away, including edits you have not published.
            {hasPublishedVersion
              ? " Your published version is not affected."
              : " You will be left with no COP for this project."}
          </p>
          <div className="draft-actions">
            <button className="danger-button" disabled={pending} onClick={() => void run("discard")} type="button">
              {pending ? "Discarding…" : "Discard the draft"}
            </button>
            <button className="secondary-button" disabled={pending} onClick={() => setMode("idle")} type="button">
              Keep editing
            </button>
          </div>
        </div>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
