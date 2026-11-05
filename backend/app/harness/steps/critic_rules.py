"""Deterministic quality heuristics.

The critic needs both signal types. Structural smells ("this process has 14
stages", "this Stage cites 19 Concepts") are mechanical and belong in code; the
critic prompt covers judgment calls.

Whether a Stage carries an example or an implementation detail is also
mechanical, so it lives here rather than in the critic prompt. Asking a model
to grade its own output on "did I write an example" produces agreement, not a
signal: the model reads its own Stage, decides it is sufficiently illustrated,
and the gap survives. `app.domain.quality` decides it instead, from the artifact.

Warnings never fail a run on their own, except where a later publish gate makes
them blocking for new candidates.
"""

from typing import Any

from app.domain.quality import (
    CONCEPT_FRAME_CODES,
    L2,
    blocking_issues,
    concept_frame_issues,
)
from app.domain.quality import check_artifact as check_operational_completeness

VAGUE_GOAL_PREFIXES = ("learn", "understand", "study", "know about", "get familiar")
MAX_REASONABLE_STAGES = 10
MAX_REASONABLE_CONCEPTS_PER_STAGE = 12
LOW_LEVEL_OPERATION_TOKENS = (
    "set_",
    "get_",
    "put_",
    "call_",
    "click_",
    "import_",
    "await ",
)
MIN_EXPANSION_COUNT = 2

#: L2 codes that make a run `needs_attention` rather than `completed`.
#: Structure is already validated by H120; these are the cases where a
#: structurally perfect artifact is still not something a learner can act on.
CONTENT_GATE_CODES = frozenset(
    {
        "MISSING_STAGE_EXAMPLE",
        "MISSING_IMPLEMENTATION_DETAIL",
        "IMPLEMENTATION_DETAIL_NOT_ACTIONABLE",
        "SETUP_NOT_ACTIONABLE",
        "MISSING_VALIDATION_STEP",
    }
)


def content_issues(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """L2 content-contract findings, shaped like every other critic issue.

    `entity_ref` is the Stage or Operation id, so H110 can repair exactly the
    entity that is broken instead of the whole artifact.
    """
    return [
        {
            "code": issue.code,
            "entity_ref": issue.entity_ref,
            "entity_type": issue.entity_type,
            "level": issue.level,
            "explanation": issue.explanation,
            "recommended_change": issue.recommended_change,
        }
        for issue in check_operational_completeness(artifact, levels=[L2])
    ]


def content_gate_failures(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Findings that require candidate attention and are reported before publication."""
    return [
        issue.as_dict()
        for issue in blocking_issues(check_operational_completeness(artifact, levels=[L2]))
    ]


def concept_frame_failures(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Concept-frame defects that a reader cannot work around.

    Kept separate from `content_gate_failures` on purpose: the L2 gate is about a
    Stage the learner cannot act on, while this one is about the structure the
    whole route leans on. They reach the same `needs_attention` status but are
    reported by name so a repair can target the concept instead of a Stage.
    """
    return [issue.as_dict() for issue in concept_frame_issues(artifact)]


def check_artifact(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Return heuristic issues with stable codes."""
    issues: list[dict[str, Any]] = []
    goals = artifact.get("goals") or []
    processes = artifact.get("main_processes") or []
    stages = artifact.get("stages") or []
    concepts = artifact.get("concepts") or []
    practices = artifact.get("practices") or []

    for goal in goals:
        title = str(goal.get("title", "")).strip().lower()
        outcome = str(goal.get("outcome", "")).strip()
        if title.startswith(VAGUE_GOAL_PREFIXES) and len(outcome) < 30:
            issues.append(
                {
                    "code": "GOAL_TOO_VAGUE",
                    "entity_ref": str(goal.get("id", "")),
                    "explanation": "The Goal is phrased as a learning topic with a thin outcome.",
                    "recommended_change": "Restate the Goal as a verifiable capability result.",
                }
            )

    for process in processes:
        count = len(process.get("stage_refs") or [])
        if count > MAX_REASONABLE_STAGES:
            issues.append(
                {
                    "code": "STAGE_TOO_BROAD",
                    "entity_ref": str(process.get("id", "")),
                    "explanation": (
                        f"The Main Process has {count} stages, which hides the main line."
                    ),
                    "recommended_change": "Group the stages or split the process.",
                }
            )
            continue
        for ref in process.get("stage_refs") or []:
            stage = next((item for item in stages if item.get("id") == ref), None)
            if stage is None:
                continue
            if len(stage.get("concept_refs") or []) > MAX_REASONABLE_CONCEPTS_PER_STAGE:
                issues.append(
                    {
                        "code": "CONCEPT_OVERPROMOTED",
                        "entity_ref": str(stage.get("id", "")),
                        "explanation": (
                            f"The Stage promotes {len(stage['concept_refs'])} Concepts, "
                            "which reads like a glossary."
                        ),
                        "recommended_change": (
                            "Demote the least reused Concepts to implementation detail."
                        ),
                    }
                )

    for operation in artifact.get("operations") or []:
        name = str(operation.get("name", "")).strip().lower()
        if name.startswith(LOW_LEVEL_OPERATION_TOKENS) or "()" in name:
            issues.append(
                {
                    "code": "OPERATION_TOO_LOW_LEVEL",
                    "entity_ref": str(operation.get("id", "")),
                    "explanation": (
                        "The Operation looks like raw API syntax rather than a meaningful action."
                    ),
                    "recommended_change": (
                        "Collapse it into a higher-value Operation above API syntax."
                    ),
                }
            )

    if not practices:
        issues.append(
            {
                "code": "WEAK_PRACTICE",
                "entity_ref": "artifact",
                "explanation": "No Minimal Practice is attached, so the COP cannot be exercised.",
                "recommended_change": "Add one practice that traverses a full Main Process.",
            }
        )

    if not artifact.get("expansion_map"):
        issues.append(
            {
                "code": "OVERSIMPLIFIED",
                "entity_ref": "artifact",
                "explanation": "The Expansion Map is empty, so the learner has no next step.",
                "recommended_change": "Add at least two expansion directions.",
            }
        )

    if len(concepts) > 20:
        issues.append(
            {
                "code": "ENCYCLOPEDIA_DRIFT",
                "entity_ref": "artifact",
                "explanation": (
                    f"{len(concepts)} Concepts suggests reference coverage over structure."
                ),
                "recommended_change": "Remove Concepts that no Stage actually uses.",
            }
        )

    # Content contract last, so the structural findings are read first. These
    # carry a `level` and an `entity_type` the older codes do not need.
    issues.extend(content_issues(artifact))
    issues.extend(concept_frame_failures(artifact))

    return issues


def merged_report(
    heuristic_issues: list[dict[str, Any]],
    model_report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combine code heuristics with the model critic report.

    The model can downgrade an issue but never silence a structural one: code
    findings are kept and only deduplicated.
    """
    model_issues = [
        issue
        for issue in (model_report or {}).get("issues") or []
        if isinstance(issue, dict) and issue.get("code")
    ]
    seen = {(issue["code"], issue.get("entity_ref")) for issue in heuristic_issues}
    combined = list(heuristic_issues)
    for issue in model_issues:
        key = (str(issue.get("code")), str(issue.get("entity_ref") or ""))
        if key not in seen:
            seen.add(key)
            combined.append(issue)

    severity = str((model_report or {}).get("severity", "pass"))
    if any(
        issue["code"] in {"ENCYCLOPEDIA_DRIFT", "API_MANUAL_DRIFT", "STAGE_TOO_BROAD"}
        for issue in combined
    ):
        severity = "major"
    elif any(issue["code"] in CONTENT_GATE_CODES for issue in combined):
        # A Stage a reader cannot act on is not a stylistic nit. The refiner has
        # to run, otherwise the candidate ships exactly as unusable as it was.
        severity = "major"
    elif any(issue["code"] in CONCEPT_FRAME_CODES for issue in combined):
        # A definition that only repeats its own label leaves the reader with a
        # glossary, not a frame. Also major: it must reach the refiner.
        severity = "major"
    elif combined and severity == "pass":
        severity = "minor"
    return {"severity": severity, "issues": combined}
