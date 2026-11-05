import type { PublicationFindings } from "../lib/api";

export function hasPublicationWarnings(findings: PublicationFindings): boolean {
  return Boolean(findings.content_gate?.length || findings.concept_frame?.length || findings.unresolved_evidence?.length);
}

/** Render server findings; do not duplicate domain quality rules in the client. */
export function PublicationWarnings({ findings, published = false }: { findings: PublicationFindings; published?: boolean }) {
  if (!hasPublicationWarnings(findings)) return null;
  const issues = [...(findings.content_gate ?? []), ...(findings.concept_frame ?? [])];
  return (
    <section className="publication-warnings" aria-label="Publication warnings">
      <h3>{published ? "Content warnings" : "Review before publishing"}</h3>
      <p>These checks found incomplete content. They do not verify factual accuracy. {published ? "This version was saved with the following warnings." : "You can keep editing or publish with these warnings."}</p>
      <ul>
        {issues.map((issue) => (
          <li key={`${issue.code}:${issue.entity_ref}`}>
            <strong>{issue.entity_ref}</strong>: {issue.explanation}
            <p>{issue.recommended_change}</p>
          </li>
        ))}
        {(findings.unresolved_evidence ?? []).map((ref, index) => (
          <li key={`source:${ref.entity_ref}:${ref.source_id}:${index}`}>
            <strong>{ref.entity_ref}</strong>: Source {ref.source_id} is unavailable in this project. Review this citation.
          </li>
        ))}
      </ul>
    </section>
  );
}
