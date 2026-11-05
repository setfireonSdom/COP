import type { COPArtifact } from "@cop-studio/cop-types";

import type {
  GenerationRequest,
  GenerationRun,
  RunProgress,
} from "./generation-api";

export interface ProjectSummary {
  id: string;
  title: string;
  description: string;
  domain: string;
  scope: string;
  preferred_language: string;
  status: "active" | "archived" | "deleted";
  created_at: string;
  updated_at: string;
  latest_version: number | null;
}

export interface VersionSummary {
  id: string;
  project_id: string;
  version_number: number;
  /** Null for the first published version; set on every later one. */
  parent_version_id: string | null;
  run_id: string | null;
  change_summary: string;
  created_by: "user" | "harness" | "mixed";
  created_at: string;
}

export interface PublicationIssue {
  code: string;
  entity_ref: string;
  explanation: string;
  recommended_change: string;
}

export interface PublicationFindings {
  content_gate?: PublicationIssue[] | null;
  concept_frame?: PublicationIssue[] | null;
  unresolved_evidence?: { entity_ref: string; collection: string; source_id: string }[] | null;
}

export interface PublishCheck extends PublicationFindings {
  updated_at: string;
}

export type PublishResult = VersionSummary & PublicationFindings;

export interface ResolvedSource {
  id: string;
  title: string;
  type: string;
  uri: string | null;
  status: string;
}

export interface VersionDetail extends VersionSummary {
  artifact: COPArtifact;
  /**
   * `evidence_ref.source_id` -> the project Source it resolves to.
   *
   * Resolved by the backend because "can this citation be opened" depends on the
   * project's sources, which the browser cannot see. A ref absent from this map
   * is unresolvable, and the UI says so rather than hiding the citation.
   */
  evidence_sources: Record<string, ResolvedSource>;
}

export interface DraftCounts {
  goals: number;
  processes: number;
  stages: number;
  concepts: number;
  operations: number;
  shared_foundations: number;
  practices: number;
}

export interface DraftSummary {
  id: string;
  project_id: string;
  base_version_id: string | null;
  source_run_id: string | null;
  updated_at: string;
  title: string;
  counts: DraftCounts;
}

export interface DraftDetail extends DraftSummary {
  artifact: COPArtifact;
}

/** API path segment -> editable field names, mirroring backend `EDITABLE_FIELDS`. */
export const DRAFT_EDITABLE_FIELDS = {
  goals: ["title", "outcome", "why_it_matters"],
  processes: ["title", "outcome"],
  stages: [
    "title",
    "local_goal",
    "why_it_exists",
    "local_outcome",
    "example",
    "implementation_details",
  ],
  concepts: ["name", "definition", "role"],
  operations: ["name", "definition", "purpose", "common_failures"],
} as const satisfies Record<string, readonly string[]>;

export type DraftEntityKind = keyof typeof DRAFT_EDITABLE_FIELDS;

/**
 * Entity kinds the model may refine, mapped from the plural API segment to the
 * singular domain type the run API expects. Concepts and Operations are
 * deliberately absent: V1 refines Goals, Main Processes, and Stages only.
 */
export const REFINABLE_KINDS: Partial<Record<DraftEntityKind, "goal" | "process" | "stage">> = {
  goals: "goal",
  processes: "process",
  stages: "stage",
};

export type RefinableKind = NonNullable<(typeof REFINABLE_KINDS)[DraftEntityKind]>;

export interface SourceSummary {
  id: string;
  project_id: string;
  type: "text" | "txt" | "markdown" | "pdf" | "url";
  title: string;
  original_uri: string | null;
  status: "created" | "processing" | "ready" | "failed";
  metadata: Record<string, unknown>;
  char_count: number | null;
  preview: string | null;
  created_at: string;
  updated_at: string;
}

export interface AppSettings {
  provider: {
    type: "mock" | "openai_compatible";
    base_url: string;
    model: string;
    timeout: number;
    max_retries: number;
    mock_scenario: "success" | "invalid" | "timeout" | "rate_limit" | "slow";
    has_api_key: boolean;
    api_key_hint: string | null;
  };
  generation: {
    language: string;
    generation_depth: "fast" | "standard" | "deep";
    learner_level: "new" | "some_experience" | "advanced";
    detail_density: "compact" | "balanced" | "detailed";
    practice_mode: "off" | "priority" | "all";
    evidence_density: "minimal" | "key_claims" | "high";
  };
  appearance: { theme: "system" | "light" | "dark"; density: "comfortable" | "compact" };
}

/**
 * What a project's settings override, and what those resolve to.
 *
 * `overrides` is the project's own layer only; `effective` is the merged result.
 * The UI needs both: a control has to show the value that will actually be used
 * *and* say whether it came from the project or is merely inheriting an app
 * default, otherwise the two are indistinguishable.
 */
export interface ProjectSettingsView {
  overrides: { generation?: Partial<AppSettings["generation"]> };
  effective: AppSettings;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export type ExportFormat = "json" | "markdown" | "markdown_bundle";

export async function exportVersion(
  versionId: string,
  format: ExportFormat,
): Promise<{ blob: Blob; filename: string }> {
  const path = `/versions/${encodeURIComponent(versionId)}/exports`;
  const response = await fetch(`${publicApiBaseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format }),
  });
  if (!response.ok) throw await errorFrom(response, path);
  const disposition = response.headers.get("content-disposition") ?? "";
  const encoded = disposition.match(/filename\*=utf-8''([^;]+)/i)?.[1];
  const quoted = disposition.match(/filename="?([^";]+)"?/i)?.[1];
  const fallback = format === "json" ? "cop.json" : format === "markdown" ? "cop.md" : "cop.zip";
  return {
    blob: await response.blob(),
    filename: encoded ? decodeURIComponent(encoded) : quoted ?? fallback,
  };
}

async function errorFrom(response: Response, path: string): Promise<ApiError> {
  const payload = (await response.json().catch(() => null)) as
    | { detail?: string; error?: { code: string; message: string } }
    | null;
  if (payload?.error?.message) {
    return new ApiError(response.status, payload.error.message);
  }
  if (typeof payload?.detail === "string") {
    return new ApiError(response.status, payload.detail);
  }
  return new ApiError(response.status, `COP Studio API returned ${response.status} for ${path}`);
}

function baseUrl(): string {
  // Browser reads use the same public proxy as writes, including production
  // builds without NEXT_PUBLIC_API_BASE_URL. Internal URLs belong to Node.
  if (typeof window !== "undefined") return publicApiBaseUrl();
  const configured =
    process.env.INTERNAL_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;

  // A relative base is the browser's own path to the API. `fetch` resolves it
  // against the page origin, so the proxy handles it and no host is involved.
  // Returning an absolute URL here instead would send the browser off-origin to
  // whatever port happened to be configured.
  if (configured) return configured;

  // Nothing configured at all: this is a Node caller, not a request. The E2E
  // suite imports this module directly, and a fixed port is wrong on this
  // machine because 8000 belongs to an unrelated service -- the request would
  // succeed and report a missing project, which reads as a product bug.
  if (process.env.E2E_BASE_URL) {
    return `${process.env.E2E_BASE_URL.replace(/\/$/, "")}/api/v1`;
  }
  return "http://localhost:8000/api/v1";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl()}${path}`, { cache: "no-store", ...init });
  if (!response.ok) {
    throw await errorFrom(response, path);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Server-rendered reads stay on the internal URL; writes go to the public one. */
async function post<T>(path: string, body?: unknown): Promise<T> {
  return send<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${publicApiBaseUrl()}${path}`, {
    ...init,
    headers: init.body ? { "Content-Type": "application/json", ...init.headers } : init.headers,
  });
  if (!response.ok) {
    throw await errorFrom(response, path);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getProjects(): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>("/projects");
}

/**
 * Archived projects, kept separate from the active list.
 *
 * `status=archived` rather than `include_archived=true`, which would return both
 * and force the caller to filter a list it cannot tell apart. Archive without a
 * way back is indistinguishable from losing the work.
 */
export function getArchivedProjects(): Promise<ProjectSummary[]> {
  return request<ProjectSummary[]>("/projects?status=archived");
}

export function restoreProject(projectId: string): Promise<ProjectSummary> {
  return send<ProjectSummary>(`/projects/${encodeURIComponent(projectId)}/restore`, {
    method: "POST",
  });
}

/** Lifecycle transport is shared by entry points; confirmation belongs to UI. */
export function archiveProject(projectId: string): Promise<ProjectSummary> {
  return send<ProjectSummary>(`/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH", body: JSON.stringify({ status: "archived" }),
  });
}

/** Existing backend semantics: hide from the app, not a physical data purge. */
export function deleteProject(projectId: string): Promise<void> {
  return send<void>(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
}

export function getProject(projectId: string): Promise<ProjectSummary> {
  return request<ProjectSummary>(`/projects/${encodeURIComponent(projectId)}`);
}

export function getLatestVersion(projectId: string): Promise<VersionDetail> {
  return request<VersionDetail>(
    `/projects/${encodeURIComponent(projectId)}/versions/latest`,
  );
}

export function getVersions(projectId: string): Promise<VersionSummary[]> {
  return request<VersionSummary[]>(`/projects/${encodeURIComponent(projectId)}/versions`);
}

export function getVersion(versionId: string): Promise<VersionDetail> {
  return request<VersionDetail>(`/versions/${encodeURIComponent(versionId)}`);
}

export function getProjectSettings(projectId: string): Promise<ProjectSettingsView> {
  return request<ProjectSettingsView>(`/projects/${encodeURIComponent(projectId)}/settings`);
}

/**
 * The settings a run would use, merged by the backend.
 *
 * `override` is the run-scoped layer. Passing it lets the panel preview exactly
 * what a run would receive, computed by the same code path that will execute it
 * rather than by a second merge in the browser.
 */
export async function getEffectiveGenerationSettings(
  projectId: string,
  override?: Record<string, unknown>,
): Promise<{ effective: AppSettings["generation"]; harness_view: Record<string, unknown> }> {
  const query = override ? `?run=${encodeURIComponent(JSON.stringify(override))}` : "";
  return request<{ effective: AppSettings["generation"]; harness_view: Record<string, unknown> }>(
    `/projects/${encodeURIComponent(projectId)}/generation-settings${query}`,
  );
}

export interface PatchChange {
  field: string;
  before: string;
  after: string;
}

export interface RejectedProposal {
  field: string;
  reason: string;
  value: string;
}

export type PatchState =
  | "idle"
  | "generating"
  | "ready"
  | "accepted"
  | "rejected"
  | "expired";

export interface CandidatePatch {
  run_id: string;
  state: PatchState;
  project_id: string;
  entity_type: string;
  entity_id: string;
  entity_title: string;
  changes: PatchChange[];
  rejected: RejectedProposal[];
  locked_paths: string[];
  /** True when the draft moved on since the proposal was made. */
  stale: boolean;
}

export interface PatchResult {
  state: PatchState;
  draft_id: string | null;
  applied_fields: string[];
  skipped: RejectedProposal[];
  message: string;
}

export function getCandidatePatch(runId: string): Promise<CandidatePatch> {
  return request<CandidatePatch>(
    `/generation-runs/${encodeURIComponent(runId)}/candidate-patch`,
  );
}

export function acceptCandidatePatch(runId: string): Promise<PatchResult> {
  return post<PatchResult>(
    `/generation-runs/${encodeURIComponent(runId)}/candidate-patch/accept`,
  );
}

export function rejectCandidatePatch(runId: string): Promise<PatchResult> {
  return post<PatchResult>(
    `/generation-runs/${encodeURIComponent(runId)}/candidate-patch/reject`,
  );
}

export async function getCandidatePatchOrNull(runId: string): Promise<CandidatePatch | null> {
  try {
    return await getCandidatePatch(runId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) return null;
    throw error;
  }
}

/**
 * The project's active draft, or null when there is none.
 *
 * A 404 is an ordinary state here, not a failure: most of the time a project has
 * no draft, so this must not throw or every page would need a try/catch.
 */
export async function getDraft(projectId: string): Promise<DraftDetail | null> {
  try {
    return await request<DraftDetail>(`/projects/${encodeURIComponent(projectId)}/draft`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function createDraftFromRun(projectId: string, runId: string): Promise<DraftDetail> {
  return post<DraftDetail>(
    `/projects/${encodeURIComponent(projectId)}/drafts/from-run/${encodeURIComponent(runId)}`,
  );
}

export function createDraftFromVersion(
  projectId: string,
  versionId: string,
): Promise<DraftDetail> {
  return post<DraftDetail>(
    `/projects/${encodeURIComponent(projectId)}/drafts/from-version/${encodeURIComponent(versionId)}`,
  );
}

export function checkDraftPublication(draftId: string): Promise<PublishCheck> {
  return request<PublishCheck>(`/drafts/${encodeURIComponent(draftId)}/publish-check`);
}

export function publishDraft(
  draftId: string,
  changeSummary: string,
  reviewedUpdatedAt?: string,
): Promise<PublishResult> {
  return post<PublishResult>(`/drafts/${encodeURIComponent(draftId)}/publish`, {
    change_summary: changeSummary,
    reviewed_updated_at: reviewedUpdatedAt,
  });
}

export function discardDraft(draftId: string): Promise<void> {
  return send<void>(`/drafts/${encodeURIComponent(draftId)}`, { method: "DELETE" });
}

export function patchDraftEntity(
  draftId: string,
  kind: DraftEntityKind,
  entityId: string,
  changes: Record<string, string>,
): Promise<DraftSummary> {
  return send<DraftSummary>(
    `/drafts/${encodeURIComponent(draftId)}/${kind}/${encodeURIComponent(entityId)}`,
    { method: "PATCH", body: JSON.stringify(changes) },
  );
}

export function patchDraftMetadata(
  draftId: string,
  changes: Record<string, unknown>,
): Promise<DraftSummary> {
  return send<DraftSummary>(`/drafts/${encodeURIComponent(draftId)}/metadata`, {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
}

export function getProjectSources(projectId: string): Promise<SourceSummary[]> {
  return request<SourceSummary[]>(`/projects/${encodeURIComponent(projectId)}/sources`);
}

export function getAppSettings(): Promise<AppSettings> {
  return request<AppSettings>("/settings");
}

export function publicApiBaseUrl(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";
}

export async function startGenerationRun(
  projectId: string,
  body: GenerationRequest,
): Promise<GenerationRun> {
  return post<GenerationRun>(
    `/projects/${encodeURIComponent(projectId)}/generation-runs`,
    body,
  );
}

export async function getGenerationRun(runId: string): Promise<GenerationRun> {
  return request<GenerationRun>(
    `/generation-runs/${encodeURIComponent(runId)}`,
  );
}

export async function getRunProgress(runId: string): Promise<RunProgress> {
  return request<RunProgress>(
    `/generation-runs/${encodeURIComponent(runId)}/progress`,
  );
}

/**
 * Most recent runs for a project, newest first.
 *
 * The panel used to hold its run id only in component state, so leaving the page
 * and coming back showed the "start a new run" form while a run was still
 * running or had already finished. The server knows; the browser has to ask.
 */
export async function listGenerationRuns(projectId: string): Promise<GenerationRun[]> {
  return request<GenerationRun[]>(
    `/projects/${encodeURIComponent(projectId)}/generation-runs`,
  );
}

export async function cancelGenerationRun(runId: string): Promise<GenerationRun> {
  return post<GenerationRun>(`/generation-runs/${encodeURIComponent(runId)}/cancel`);
}

export async function resumeGenerationRun(
  runId: string, expectedAttempt: number, timeoutSeconds?: number,
): Promise<GenerationRun> {
  return post<GenerationRun>(`/generation-runs/${encodeURIComponent(runId)}/resume`, {
    expected_attempt: expectedAttempt, timeout_seconds: timeoutSeconds,
  });
}

/**
 * URL of the SSE progress stream.
 *
 * EventSource cannot send custom headers, so `Last-Event-ID` is passed as a
 * query parameter; the server accepts either form on reconnect.
 */
export function generationEventsUrl(runId: string, lastEventId?: number): string {
  const base = `${publicApiBaseUrl()}/generation-runs/${encodeURIComponent(runId)}/events`;
  return lastEventId === undefined ? base : `${base}?last_event_id=${lastEventId}`;
}

export async function getWorkspace(projectId: string) {
  const [project, version] = await Promise.all([
    getProject(projectId),
    getLatestVersion(projectId),
  ]);
  return { project, version, artifact: version.artifact };
}

/**
 * Project, latest published version, and the active draft if one exists.
 *
 * The draft is optional, so the version fetch is allowed to 404 as well: a
 * project with neither a version nor a draft is the pre-M4 setup state.
 */
export type StageStatus = "not_started" | "in_progress" | "completed";

export interface StageProgress {
  stage_id: string;
  status: StageStatus;
  notes: string | null;
  updated_at: string | null;
}

export interface CheckpointProgress {
  question: string;
  answer: string | null;
  updated_at: string | null;
}

export interface PracticeProgress {
  practice_id: string;
  title: string;
  status: StageStatus;
  checkpoints: CheckpointProgress[];
  updated_at: string | null;
}

export interface FoundationProgress {
  stage_id: string;
  status: StageStatus;
  updated_at: string | null;
}

export interface GoalProgress {
  goal_id: string;
  title: string;
  /** Derived from Foundation, Stage, and Practice rows, never stored. */
  completed: boolean;
  total_stages: number;
  completed_stages: number;
  /**
   * What still stands between this Goal and complete, in the order a learner
   * meets it. A Goal with an empty progress bar and no stated reason reads as a
   * broken bar rather than as unfinished work.
   */
  blocked_by: string[];
  stages: StageProgress[];
  practice: PracticeProgress | null;
}

export interface LearningProgress {
  project_id: string;
  version_id: string;
  version_number: number;
  goals: GoalProgress[];
  /**
   * The Shared Foundation, recorded once per version rather than once per Goal
   * that starts at it. A Foundation Stage belongs to no Goal, which is what stops
   * the same setup being tracked N times.
   */
  foundations: FoundationProgress[];
  completed_goals: number;
  total_goals: number;
}

// Exported for the E2E suite, which reads progress directly rather than
// reimplementing the query in a test helper.
export function getLearningProgress(
  projectId: string,
  versionId?: string,
): Promise<LearningProgress> {
  const query = versionId ? `?version_id=${encodeURIComponent(versionId)}` : "";
  return request<LearningProgress>(
    `/projects/${encodeURIComponent(projectId)}/learning-progress${query}`,
  );
}

/** The four kinds of activity one progress row can describe. */
export type ProgressKind = "stage" | "foundation" | "practice" | "checkpoint";

export interface ProgressUpdate {
  version_id: string;
  kind: ProgressKind;
  /**
   * Empty for `foundation` (a Foundation Stage belongs to no Goal) and for
   * `practice` (a Practice is keyed by its Goal). The backend rejects a
   * mismatched combination rather than storing an ambiguous row.
   */
  goal_id: string;
  /** The Stage, or for a checkpoint the exact question text. */
  stage_id?: string | null;
  status: StageStatus;
  notes?: string | null;
}

export function putLearningProgress(
  projectId: string,
  body: ProgressUpdate,
): Promise<{ status: StageStatus; kind: ProgressKind; version_id: string; stage_id: string | null }> {
  return send<{ status: StageStatus; kind: ProgressKind; version_id: string; stage_id: string | null }>(
    `/projects/${encodeURIComponent(projectId)}/learning-progress`,
    { method: "PUT", body: JSON.stringify(body) },
  );
}

export async function getProjectWorkspace(projectId: string) {
  const project = await getProject(projectId);
  const [version, draft] = await Promise.all([
    getLatestVersion(projectId).catch((error: unknown) => {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }),
    getDraft(projectId),
  ]);
  return { project, version, draft, artifact: version?.artifact ?? null };
}
