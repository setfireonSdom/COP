"""R1 — the content contract, and the gate that keeps it.

R1 asks one question: can a reader act on this COP without leaving the app?

The answer has to hold for every Stage, not for the average one, so the checks
below are per-entity rather than aggregate. A 100% coverage number produced by
one Stage carrying three details and twenty-one carrying none is the exact shape
of the failure R1 exists to close.

Three things have to agree, and each is tested separately because they fail
differently:

    the prompt   asks the model for an example and a followable method
    the schema   rejects a detail with no title, or an example with no summary
    the gate     refuses to call a candidate `completed` while one is missing

If only the prompt changed, a provider that ignores the instruction would ship a
silently incomplete COP. If only the gate changed, every real run would end in
`needs_attention` and the setting would be useless. Both, plus a repair path,
is what makes it a contract.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.quality import (
    CONCEPT_CIRCULAR_DEFINITION,
    L1,
    L2,
    MISSING_IMPLEMENTATION_DETAIL,
    MISSING_STAGE_EXAMPLE,
    MISSING_VALIDATION_STEP,
    OPERATION_WITHOUT_COMMON_FAILURES,
    SETUP_NOT_ACTIONABLE,
    blocking_issues,
    check_artifact,
    completeness_summary,
    is_setup_stage,
)
from app.harness.context import HarnessContext
from app.harness.prompts import build_stage_prompt
from app.harness.providers.mock import MockProvider
from app.harness.runner import _final_status, run_pipeline
from app.harness.steps.critic_rules import (
    concept_frame_failures,
    content_gate_failures,
    merged_report,
)
from app.harness.steps.h50_stages import normalize_detail, normalize_example, normalize_stage
from app.harness.steps.h110_refine import apply_revisions
from tests.test_harness_pipeline import FakeStore

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "cop-artifact.schema.json"


def context(**overrides: Any) -> HarnessContext:
    defaults: dict[str, Any] = {
        "run_id": "run-1",
        "project_id": "project-1",
        "input": {
            "topic": "LangChain agent development",
            "scope_hint": "Build a working agent",
            "target_outcomes": ["Ship a runnable agent"],
            "learner_level": "new",
            "source_ids": [],
        },
        "settings": {"language": "en", "generation_depth": "standard", "practice_mode": "priority"},
        "source_bundle": [
            {
                "id": "lc-overview",
                "title": "LangChain overview",
                "type": "text",
                "text": "create_agent is the high-level entry point.",
            }
        ],
    }
    defaults.update(overrides)
    return HarnessContext(**defaults)


async def generate(**overrides: Any) -> Any:
    """Run the whole pipeline on the mock provider, the way a worker does."""
    return await run_pipeline(context(**overrides), MockProvider(), FakeStore())


# --------------------------------------------------------------------------
# The prompt asks for it
# --------------------------------------------------------------------------


def test_the_stage_prompt_states_the_contract_instead_of_hinting_at_it() -> None:
    process = {
        "title": "P",
        "outcome": "O",
        "stages": [{"key": "s1", "title": "Install LangChain", "local_outcome": "installed"}],
    }
    system, _ = build_stage_prompt(process=process, stages=process["stages"], language="en")

    # A prompt that merely lists "implementation detail candidates" as one of
    # several outputs is what produced 0% coverage in the first place.
    assert "mandatory for every Stage" in system
    assert "example_candidate" in system
    assert "expected_result" in system
    assert "caution" in system
    for field in ("action", "command"):
        assert f"`{field}`" in system, f"the prompt never mentions {field}"


def test_the_prompt_calls_out_setup_stages_specifically() -> None:
    process = {
        "title": "P",
        "outcome": "O",
        "stages": [{"key": "s1", "title": "Install LangChain", "local_outcome": "installed"}],
    }
    system, _ = build_stage_prompt(process=process, stages=process["stages"], language="en")

    assert "installs, sets up, or configures" in system
    assert "both required" in system


# --------------------------------------------------------------------------
# The schema holds the shape
# --------------------------------------------------------------------------


def test_the_canonical_schema_defines_the_detail_and_example_contracts() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    defs = schema["$defs"]
    stage_props = schema["properties"]["stages"]["items"]["properties"]

    assert defs["ImplementationDetail"]["required"] == ["title"]
    for field in ("action", "command", "expected_result", "caution"):
        assert field in defs["ImplementationDetail"]["properties"]
    assert defs["Example"]["required"] == ["summary"]
    assert stage_props["implementation_details"]["items"] == {
        "$ref": "#/$defs/ImplementationDetail"
    }
    assert stage_props["example"]["oneOf"][0] == {"$ref": "#/$defs/Example"}
    # A null example stays legal, or every old published version would 500 on read.
    assert stage_props["example"]["oneOf"][1] == {"type": "null"}


def test_the_h50_output_schema_requires_an_example() -> None:
    from app.harness.schemas import STAGES_SCHEMA

    required = STAGES_SCHEMA["properties"]["stages"]["items"]["required"]

    assert "example_candidate" in required
    assert (
        "implementation_detail_candidates"
        in STAGES_SCHEMA["properties"]["stages"]["items"]["properties"]
    )


def test_h50_normalises_a_legacy_detail_rather_than_discarding_it() -> None:
    """`label`/`body` is what the mock emitted before the contract existed.

    An older provider response should be salvaged for a field-name difference,
    not thrown away, or an upgrade would silently empty every Stage.
    """
    detail = normalize_detail({"label": "Verification", "body": "Check the result."})

    assert detail == {"title": "Verification", "action": "Check the result."}


def test_h50_keeps_the_contract_fields_when_the_model_supplies_them() -> None:
    detail = normalize_detail(
        {
            "title": "Install",
            "action": "Create an environment",
            "command": "python -m venv .venv",
            "expected_result": "no output",
            "caution": "not the system interpreter",
            "note": "extra keys are kept out",
        }
    )

    assert detail["command"] == "python -m venv .venv"
    assert detail["expected_result"] == "no output"
    assert detail["caution"] == "not the system interpreter"
    assert "note" not in detail, "only the contract fields belong in a published detail"


def test_an_example_with_only_a_bare_string_is_kept_as_its_summary() -> None:
    assert normalize_example("We ran it and it printed 4.") == {
        "summary": "We ran it and it printed 4."
    }


def test_an_empty_example_stays_absent_rather_than_becoming_an_empty_object() -> None:
    assert normalize_example({}) is None
    assert normalize_example(None) is None
    assert normalize_example("   ") is None


def test_normalize_stage_produces_the_canonical_detail_shape() -> None:
    stage = normalize_stage(
        {
            "key": "s1",
            "title": "Install LangChain",
            "local_goal": "Get an environment",
            "local_outcome": "Installed",
            "operation_candidates": ["Install"],
            "implementation_detail_candidates": [
                {"title": "Install", "action": "Run pip", "command": "pip install langchain"}
            ],
            "example_candidate": {"summary": "pip reports success"},
        },
        {"key": "s1", "title": "Install", "local_outcome": "Installed", "process_key": "p1"},
        "g1",
    )

    assert stage["implementation_details"] == [
        {"title": "Install", "action": "Run pip", "command": "pip install langchain"}
    ]
    assert stage["example"] == {"summary": "pip reports success"}


# --------------------------------------------------------------------------
# The gate refuses to call it complete
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_generated_candidate_satisfies_the_content_contract() -> None:
    """The headline acceptance criterion: 100% example and detail coverage."""
    outcome = await generate()
    artifact = outcome.context.artifact
    assert artifact is not None
    summary = completeness_summary(artifact, known_source_ids={"lc-overview"})

    assert summary["coverage"]["stage_example"] == 1.0, "Stages without an example: " + ", ".join(
        s["id"] for s in artifact["stages"] if not (s.get("example") or {}).get("summary")
    )
    assert summary["coverage"]["implementation_detail"] == 1.0, (
        "Executable Stages without an implementation detail: "
        + ", ".join(
            s["id"]
            for s in artifact["stages"]
            if s.get("operation_refs") and not s.get("implementation_details")
        )
    )
    assert summary["coverage"]["operation_common_failures"] == 1.0
    assert summary["blocking"] == 0
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_the_mock_and_the_real_contract_are_the_same_contract() -> None:
    """Spec `19` requires the mock to make the acceptance path real.

    A mock that skipped the content contract would let the whole suite pass while
    the shipped product produced unusable Stages, because nothing in CI would
    ever see a real provider's answer.
    """
    outcome = await generate()
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    from jsonschema import Draft202012Validator

    errors = list(Draft202012Validator(schema).iter_errors(outcome.context.artifact))
    assert errors == [], f"the mock produces an artifact the canonical schema rejects: {errors[:1]}"


@pytest.mark.asyncio
async def test_a_concept_frame_of_labels_is_needs_attention_not_completed() -> None:
    """A structurally valid artifact can still explain nothing.

    This is the failure the L1 concept checks exist for: every Stage is
    actionable, every reference resolves, and the model a reader is supposed to
    build is a list of names. The run must not report `completed`.
    """
    good = (await generate()).context.artifact
    assert good is not None
    broken = json.loads(json.dumps(good))
    for concept in broken["concepts"]:
        concept["definition"] = concept["name"]

    gated = context()
    gated.artifact = broken

    assert _final_status(gated) == "needs_attention"
    codes = {issue["code"] for issue in concept_frame_failures(broken)}
    assert CONCEPT_CIRCULAR_DEFINITION in codes


@pytest.mark.asyncio
async def test_a_complete_candidate_reports_no_concept_frame_failures() -> None:
    """The positive control: the gate must not fire on the mock's own output."""
    outcome = await generate()
    artifact = outcome.context.artifact
    assert artifact is not None

    assert concept_frame_failures(artifact) == []
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_the_generated_candidate_has_usable_concept_explanations() -> None:
    """Prompt and gate agree: what the mock writes passes the concept contract."""
    artifact = (await generate()).context.artifact
    assert artifact is not None
    for concept in artifact["concepts"]:
        assert concept["definition"].strip()
        assert concept["definition"].strip() != concept["name"].strip()
        assert concept["role"].strip()
    assert check_artifact(artifact, levels=[L1]) == []


@pytest.mark.asyncio
async def test_a_candidate_missing_content_is_needs_attention_not_completed() -> None:
    """The gate fires on a structurally perfect but unusable artifact."""
    good = (await generate()).context.artifact
    assert good is not None
    stripped = json.loads(json.dumps(good))
    stripped["stages"][0]["implementation_details"] = []

    gated = context()
    gated.artifact = stripped

    assert _final_status(gated) == "needs_attention"
    # And the reason travels with the run rather than being a bare status.
    failures = content_gate_failures(stripped)
    assert failures[0]["code"] == MISSING_IMPLEMENTATION_DETAIL
    assert failures[0]["entity_ref"] == stripped["stages"][0]["id"]


@pytest.mark.asyncio
async def test_a_candidate_with_no_examples_is_needs_attention() -> None:
    good = (await generate()).context.artifact
    assert good is not None
    stripped = json.loads(json.dumps(good))
    for stage in stripped["stages"]:
        stage["example"] = None

    gated = context()
    gated.artifact = stripped

    assert _final_status(gated) == "needs_attention"
    codes = {issue["code"] for issue in content_gate_failures(stripped)}
    assert MISSING_STAGE_EXAMPLE in codes


@pytest.mark.asyncio
async def test_a_setup_stage_without_a_command_is_blocking() -> None:
    """`Install LangChain` with prose but no command is the R1 failure mode."""
    good = (await generate()).context.artifact
    assert good is not None
    stripped = json.loads(json.dumps(good))
    stripped["stages"][0]["title"] = "Install LangChain"
    stripped["stages"][0]["implementation_details"] = [
        {
            "title": "Install it",
            "action": "Install the library",
            "expected_result": "It is installed",
        }
    ]

    codes = {issue.code for issue in check_artifact(stripped, levels=[L2])}

    assert SETUP_NOT_ACTIONABLE in codes
    assert is_setup_stage(stripped["stages"][0])


@pytest.mark.asyncio
async def test_a_stage_with_no_validation_step_is_blocking() -> None:
    good = (await generate()).context.artifact
    assert good is not None
    stripped = json.loads(json.dumps(good))
    for detail in stripped["stages"][0]["implementation_details"]:
        detail.pop("expected_result", None)

    codes = {issue.code for issue in check_artifact(stripped, levels=[L2])}

    assert MISSING_VALIDATION_STEP in codes


def test_a_missing_content_issue_forces_the_refiner_to_run() -> None:
    """A content gap must raise severity to `major`.

    Left at `minor` the refiner would still run, but the important part is that
    a model-only critic reporting `pass` must not be able to hide a missing
    example: the code findings are merged in and cannot be downgraded.
    """
    artifact = {
        "stages": [
            {
                "id": "stage.a",
                "title": "Do the thing",
                "operation_refs": ["op"],
                "example": {"summary": "s"},
                "implementation_details": [
                    {"title": "t", "action": "a", "command": "c", "expected_result": "e"}
                ],
            }
        ],
        "operations": [{"id": "op", "name": "Op", "definition": "d", "common_failures": ["f"]}],
    }
    without_example = json.loads(json.dumps(artifact))
    without_example["stages"][0]["example"] = None

    report = merged_report(
        [
            {
                "code": MISSING_STAGE_EXAMPLE,
                "entity_ref": "stage.a",
                "explanation": "x",
                "recommended_change": "y",
            }
        ],
        {"severity": "pass", "issues": []},
    )
    clean = merged_report([], {"severity": "pass", "issues": []})

    assert report["severity"] == "major"
    assert clean["severity"] == "pass"
    assert content_gate_failures(without_example)


def test_operations_without_common_failures_are_reported_but_do_not_block_publication() -> None:
    """`common_failures` is a quality gap, not a publication blocker.

    Making it blocking would strand every run whose provider simply omitted one
    list, which is a worse failure than the gap itself.
    """
    artifact = {
        "stages": [
            {
                "id": "stage.a",
                "title": "Do it",
                "operation_refs": ["op"],
                "example": {"summary": "s"},
                "implementation_details": [{"title": "t", "action": "a", "expected_result": "e"}],
            }
        ],
        "operations": [{"id": "op", "name": "Op", "definition": "d"}],
    }

    issues = check_artifact(artifact, levels=[L2])
    codes = {issue.code for issue in issues}

    assert OPERATION_WITHOUT_COMMON_FAILURES in codes
    assert blocking_issues(issues) == []


# --------------------------------------------------------------------------
# The repair path
# --------------------------------------------------------------------------


def test_the_refiner_can_write_the_fields_the_gate_asks_for() -> None:
    """Without this, a blocked publish is a dead end for the user."""
    from app.harness.schemas import REFINABLE_FIELDS

    assert "implementation_details" in REFINABLE_FIELDS["stage"]
    assert "example" in REFINABLE_FIELDS["stage"]
    assert "common_failures" in REFINABLE_FIELDS["operation"]


def test_applying_a_detail_revision_uses_the_canonical_shape() -> None:
    artifact = {
        "stages": [{"id": "stage.a", "implementation_details": []}],
        "operations": [],
    }
    updated, applied, rejected = apply_revisions(
        artifact,
        [
            {
                "entity_type": "stage",
                "entity_key": "stage.a",
                "field": "implementation_details",
                "value": [{"title": "Install", "action": "Run pip", "command": "pip install x"}],
            }
        ],
        [],
    )

    assert rejected == []
    assert applied == ["stage.stage.a.implementation_details"]
    assert updated["stages"][0]["implementation_details"] == [
        {"title": "Install", "action": "Run pip", "command": "pip install x"}
    ]


def test_a_repaired_detail_is_not_locked_out_by_its_own_lock() -> None:
    """A user who wrote a detail by hand must not have the AI overwrite it."""
    artifact = {"stages": [{"id": "stage.a", "implementation_details": []}], "operations": []}
    updated, applied, rejected = apply_revisions(
        artifact,
        [
            {
                "entity_type": "stage",
                "entity_key": "stage.a",
                "field": "implementation_details",
                "value": [{"title": "AI", "action": "x"}],
            }
        ],
        ["stage.a.implementation_details"],
    )

    assert applied == []
    assert rejected[0]["reason"] == "path is locked by user edits"
    assert updated["stages"][0]["implementation_details"] == []


def test_a_string_where_a_list_belongs_is_coerced_not_dropped() -> None:
    """Providers answer with a bare string surprisingly often.

    Rejecting it would leave the gate reporting the same gap the repair was
    meant to close.
    """
    artifact = {"stages": [], "operations": [{"id": "op.a", "common_failures": []}]}
    updated, applied, _ = apply_revisions(
        artifact,
        [
            {
                "entity_type": "operation",
                "entity_key": "op.a",
                "field": "common_failures",
                "value": "The model is not configured",
            }
        ],
        [],
    )

    assert applied == ["operation.op.a.common_failures"]
    assert updated["operations"][0]["common_failures"] == ["The model is not configured"]


def test_an_empty_replacement_is_still_rejected() -> None:
    """Coercion must not become a way to blank a field."""
    artifact = {"stages": [{"id": "stage.a", "implementation_details": []}], "operations": []}
    _, applied, rejected = apply_revisions(
        artifact,
        [
            {
                "entity_type": "stage",
                "entity_key": "stage.a",
                "field": "implementation_details",
                "value": [{"title": "   "}],
            }
        ],
        [],
    )

    assert applied == []
    assert rejected[0]["reason"] == "replacement value is empty"


async def test_publishing_reports_content_gaps_instead_of_hiding_them(client, db) -> None:
    """R1: "no silent publication".

    A publish of an incomplete COP is allowed -- spec `15` §6 says a COP
    remains useful when incomplete, so refusing would take away a legitimate
    choice. What must not happen is the user learning about the gaps only later.
    The response therefore carries the exact findings, with the Stage ids.
    """
    import uuid as _uuid

    from app.db.models import COPVersion, Draft, Project

    project = Project(title="Incomplete", domain="d", scope="s")
    db.add(project)
    db.commit()

    artifact = json.loads(json.dumps((await generate()).context.artifact))
    assert artifact is not None
    for stage in artifact["stages"]:
        stage["example"] = None
        stage["implementation_details"] = []

    draft = Draft(project_id=project.id, artifact_json=artifact)
    db.add(draft)
    db.commit()
    db.refresh(draft)

    response = client.post(f"/api/v1/drafts/{_uuid.UUID(str(draft.id))}/publish", json={})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["version_number"] == 1, "an incomplete COP is still publishable"
    codes = {item["code"] for item in body["content_gate"]}
    assert "MISSING_STAGE_EXAMPLE" in codes
    assert "MISSING_IMPLEMENTATION_DETAIL" in codes
    # The finding names the entity, so the message is actionable.
    assert all(item["entity_ref"] for item in body["content_gate"])

    version = db.get(COPVersion, _uuid.UUID(body["id"]))
    assert version is not None, "the version is stored; the report is additive"


async def test_publishing_a_complete_cop_reports_no_gate_findings(client, db) -> None:
    """The negative control. Without it, a gate that always fires looks fine."""
    import uuid as _uuid

    from app.db.models import Draft, Project

    project = Project(title="Complete", domain="d", scope="s")
    db.add(project)
    db.commit()

    artifact = json.loads(json.dumps((await generate()).context.artifact))
    draft = Draft(project_id=project.id, artifact_json=artifact)
    db.add(draft)
    db.commit()
    db.refresh(draft)

    response = client.post(f"/api/v1/drafts/{_uuid.UUID(str(draft.id))}/publish", json={})

    assert response.status_code == 200
    assert not response.json().get("content_gate")


async def test_reading_a_version_never_carries_gate_judgements(client, db) -> None:
    """A gate field on a read would imply a check that never ran."""
    from app.db.models import COPVersion, Project

    project = Project(title="P", domain="d", scope="s")
    db.add(project)
    db.commit()
    version = COPVersion(
        project_id=project.id,
        version_number=1,
        artifact_json=json.loads(json.dumps((await generate()).context.artifact)),
        change_summary="s",
    )
    db.add(version)
    db.commit()

    listing = client.get(f"/api/v1/projects/{project.id}/versions")
    assert listing.status_code == 200
    for item in listing.json():
        assert "content_gate" not in item


@pytest.mark.asyncio
async def test_the_pipeline_writes_details_in_the_canonical_shape() -> None:
    """End to end: what the mock sends, H50 normalises, H90 publishes."""
    outcome = await generate()
    stages = (outcome.context.artifact or {})["stages"]
    allowed = {"title", "action", "command", "expected_result", "caution"}

    for stage in stages:
        assert stage["example"], f"{stage['id']} lost its example on the way through"
        for detail in stage["implementation_details"]:
            assert set(detail) <= allowed, f"{stage['id']} detail leaked {set(detail) - allowed}"
            assert detail.get("title")
            assert detail.get("action") or detail.get("command")
