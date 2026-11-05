"""H110 — Refine.

Runs only for `minor` or `major` critic severity. Enforces three rules the model
cannot be trusted with on its own:

- locked (user-authored) paths are never rewritten,
- only whitelisted leaf-content fields may change,
- corrections are local, never whole-entity rewrites.
"""

from typing import Any

from jsonschema import Draft202012Validator

from app.domain.quality import CONCEPT_UNUSED
from app.harness.context import HarnessContext, HarnessEvent, StepResult
from app.harness.prompts import build_refine_prompt
from app.harness.schemas import REFINABLE_FIELDS, REFINE_SCHEMA, revision_value_schema

COLLECTIONS = {
    "goal": "goals",
    "process": "main_processes",
    "stage": "stages",
    "concept": "concepts",
    "operation": "operations",
    "branch": "branches",
}


def _clean(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _as_string_list(value: Any) -> list[str] | None:
    """Coerce a revision value into a list of non-empty strings.

    A model asked to replace `common_failures` sometimes answers with a single
    string, or with a list of objects. Rejecting that would leave the exact
    content-contract gap the repair was meant to close.
    """
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return None
    cleaned = [_clean(item if not isinstance(item, dict) else item.get("text")) for item in items]
    result = [item for item in cleaned if item]
    return result or None


def _as_detail_list(value: Any) -> list[dict[str, Any]] | None:
    """Coerce a revision value into a canonical implementation-detail list.

    Reuses the H50 normaliser so a repaired detail has exactly the shape a
    generated one does. Diverging shapes here are how a Stage ends up with two
    different detail formats depending on which step wrote it.
    """
    from app.harness.steps.h50_stages import normalize_detail

    if isinstance(value, dict):
        raw_items: list[Any] = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        return None
    details = [normalize_detail(item) for item in raw_items if isinstance(item, dict)]
    # `normalize_detail` returns `{}` for a detail whose title was present but
    # blank, so filtering on the title drops those rather than publishing a
    # nameless step.
    return [detail for detail in details if detail.get("title")] or None


def is_locked(locked_paths: list[str], entity_key: str, field: str) -> bool:
    """True when a user edit owns this entity or this specific field.

    Entity IDs already carry their own type prefix (`goal.x`, `stage.x`), so a
    lock is either the whole entity (`goal.x`) or one field of it
    (`goal.x.why_it_matters`). A lock on one field must not block the others.
    """
    field_path = f"{entity_key}.{field}"
    return any(locked in (entity_key, field_path) for locked in locked_paths)


def apply_revisions(
    artifact: dict[str, Any],
    revisions: list[dict[str, Any]],
    locked_paths: list[str],
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """Apply revisions to a copy of the artifact.

    Returns (new_artifact, applied, rejected).
    """
    import copy

    updated = copy.deepcopy(artifact)
    applied: list[str] = []
    rejected: list[dict[str, Any]] = []
    index_cache: dict[str, dict[str, dict[str, Any]]] = {}

    for revision in revisions:
        entity_type = str(revision.get("entity_type", ""))
        entity_key = str(revision.get("entity_key", ""))
        field = str(revision.get("field", ""))
        value = revision.get("value")
        collection = COLLECTIONS.get(entity_type)
        if collection is None or not entity_key or not field:
            rejected.append({**revision, "reason": "unknown entity type or field"})
            continue
        if field not in REFINABLE_FIELDS[entity_type]:
            rejected.append({**revision, "reason": f"'{field}' is not refinable"})
            continue
        if is_locked(locked_paths, entity_key, field):
            rejected.append({**revision, "reason": "path is locked by user edits"})
            continue

        if collection not in index_cache:
            index_cache[collection] = {
                str(entity.get("id")): entity for entity in updated.get(collection) or []
            }
        entity = index_cache[collection].get(entity_key)
        if entity is None:
            rejected.append({**revision, "reason": "entity id not found in artifact"})
            continue

        if field == "example" and entity_type == "stage":
            replacement = value if isinstance(value, dict) else {"summary": _clean(value)}
        elif field == "implementation_details" and entity_type == "stage":
            replacement = _as_detail_list(value)
        elif field == "common_failures" and entity_type == "operation":
            replacement = _as_string_list(value)
        else:
            if not isinstance(value, str) or not value.strip():
                rejected.append({**revision, "reason": "replacement value is empty"})
                continue
            replacement = value.strip()

        if replacement is None:
            rejected.append({**revision, "reason": "replacement value is empty"})
            continue
        if not Draft202012Validator(revision_value_schema(entity_type, field)).is_valid(
            replacement
        ):
            rejected.append({**revision, "reason": "replacement value has an invalid shape"})
            continue
        entity[field] = replacement
        applied.append(f"{entity_type}.{entity_key}.{field}")

    return updated, applied, rejected


class RefineStep:
    name = "H110"

    async def execute(self, ctx: HarnessContext, services: Any) -> StepResult:
        artifact = ctx.require("artifact")
        report = ctx.require("critic_report")
        severity = str(report.get("severity", "pass"))
        if severity == "pass":
            return StepResult.success(
                {},
                events=[HarnessEvent("step.completed", {"step": self.name, "skipped": True})],
                metrics={"skipped": True},
            )

        all_issues = report.get("issues") or []
        manual = [issue for issue in all_issues if issue.get("code") == CONCEPT_UNUSED]
        issues = [issue for issue in all_issues if issue.get("code") != CONCEPT_UNUSED]
        manual_warnings = [
            f"Concept '{issue.get('entity_ref')}' needs structural review; text-only repair "
            "cannot change bindings or remove Concepts."
            for issue in manual
        ]
        if manual and not issues:
            return StepResult.success(
                {},
                events=[HarnessEvent("step.completed", {"step": self.name, "skipped": True})],
                warnings=manual_warnings,
                metrics={"skipped": True, "manual_review": len(manual)},
            )
        locked_paths = list(ctx.locked_paths or [])
        language = ctx.settings.get("language", "auto")
        system, user = build_refine_prompt(
            artifact=artifact, issues=issues, locked_paths=locked_paths, language=language
        )
        payload = await services.complete_structured(
            system_prompt=system, user_prompt=user, schema=REFINE_SCHEMA
        )

        updated, applied, rejected = apply_revisions(
            artifact, payload.get("revisions") or [], locked_paths
        )
        warnings = manual_warnings + [
            f"Refiner proposal skipped: {item.get('reason')}" for item in rejected
        ]
        return StepResult.success(
            {"artifact": updated},
            events=[
                HarnessEvent(
                    "step.completed",
                    {
                        "step": self.name,
                        "severity": severity,
                        "applied": len(applied),
                        "rejected": len(rejected),
                    },
                )
            ],
            warnings=warnings,
            metrics={"applied": len(applied), "rejected": len(rejected)},
        )
