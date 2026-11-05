"""The concept frame is load-bearing structure, not a glossary.

These tests pin the mechanical boundary: they reject definitions that cannot be
used to reason, and they deliberately do not claim to judge whether a correct-
looking definition is *true*. A source check is a different gate.
"""

import json
from pathlib import Path

import pytest

from app.domain.quality import (
    CONCEPT_CIRCULAR_DEFINITION,
    CONCEPT_FRAME_CODES,
    CONCEPT_MISSING_EXPLANATION,
    CONCEPT_MISSING_ROLE,
    CONCEPT_UNUSED,
    L1,
    check_artifact,
)
from app.harness.steps.critic_rules import (
    concept_frame_failures,
    content_gate_failures,
    merged_report,
)

ROOT = Path(__file__).resolve().parents[2]

USABLE = (
    "The interpreter and the installed packages that actually execute this "
    "script, not any other Python on the machine."
)
ROLE = (
    "Determines which imports resolve, so it must be fixed before an import "
    "error is taken to mean the code is wrong."
)


def artifact(concepts, *, stage_concepts=None, operations=None):
    return {
        "concepts": concepts,
        "stages": [
            {
                "id": "stage.run",
                "title": "Run the script",
                "concept_refs": list(stage_concepts if stage_concepts is not None else []),
                "operation_refs": [],
                "example": {"summary": "The script prints a result."},
            }
        ],
        "operations": list(operations or []),
    }


def concept(identifier="concept.runtime", name="Runtime", definition=USABLE, role=ROLE):
    return {"id": identifier, "name": name, "definition": definition, "role": role}


def codes(payload):
    return {issue.code for issue in check_artifact(payload, levels=[L1])}


@pytest.mark.parametrize(
    "definition",
    ["d", "", "   ", "r", "thing", "concept", "一种东西", "TODO", "待补充", "x" * 20],
)
def test_a_placeholder_definition_is_not_an_explanation(definition):
    assert CONCEPT_MISSING_EXPLANATION in codes(
        artifact([concept(definition=definition)], stage_concepts=["concept.runtime"])
    )


@pytest.mark.parametrize("definition", ["停止等待响应前允许的最长时间", "A stored value."])
def test_short_definitions_are_not_rejected_merely_for_their_length(definition):
    assert CONCEPT_MISSING_EXPLANATION not in codes(
        artifact([concept(definition=definition)], stage_concepts=["concept.runtime"])
    )


def test_an_empty_role_is_reported_because_the_route_dependency_is_invisible():
    assert CONCEPT_MISSING_ROLE in codes(
        artifact([concept(role="")], stage_concepts=["concept.runtime"])
    )


@pytest.mark.parametrize(
    "name, definition",
    [
        ("Runtime", "Runtime"),
        ("Runtime", "The Runtime concept."),
        ("Runtime", "runtime"),
        ("Runtime", "Runtime is the concept of the Runtime thing."),
        ("Runtime", "This is a Runtime concept."),
        ("观察与推断", "观察与推断"),
        ("观察与推断", "这个术语是观察与推断。"),
        ("观察与推断", "一种观察与推断的东西。"),
    ],
)
def test_a_definition_that_restates_its_own_name_is_circular(name, definition):
    assert CONCEPT_CIRCULAR_DEFINITION in codes(
        artifact(
            [
                concept(
                    name=name,
                    definition=definition,
                    role="Used to separate material from explanation.",
                )
            ],
            stage_concepts=["concept.runtime"],
        )
    )


@pytest.mark.parametrize(
    "name, definition",
    [
        ("Runtime", "The interpreter and packages that execute this script."),
        ("Runtime", "A runtime environment is not the same as the source file."),
        ("观察与推断", "观察是能指回某条材料的内容；推断是你据此提出的解释。"),
        ("AI", "A chair supports a seated person."),
    ],
)
def test_a_real_explanation_mentioning_the_name_is_not_circular(name, definition):
    assert CONCEPT_CIRCULAR_DEFINITION not in codes(
        artifact([concept(name=name, definition=definition)], stage_concepts=["concept.runtime"])
    )


def test_an_unused_concept_is_a_glossary_entry_not_a_frame_member():
    orphans = codes(
        artifact(
            [
                concept(),
                concept(
                    identifier="concept.orphan",
                    name="Orphan",
                    definition="An entry that no Stage or Operation ever references.",
                ),
            ],
            stage_concepts=["concept.runtime"],
        )
    )

    assert CONCEPT_UNUSED in orphans


def test_relations_alone_do_not_make_two_orphans_useful():
    """Two Concepts pointing at each other are still a glossary."""
    payload = artifact(
        [
            concept(definition="The interpreter that executes this script."),
            concept(
                identifier="concept.other",
                name="Other",
                definition="A second unexplained entry.",
            ),
        ]
    )
    payload["concepts"][0]["related_concept_refs"] = ["concept.other"]
    payload["concepts"][1]["related_concept_refs"] = ["concept.runtime"]

    assert CONCEPT_UNUSED in codes(payload)


@pytest.mark.parametrize("bound", [False, True])
def test_only_a_stage_bound_operation_counts_as_concept_usage(bound):
    payload = artifact(
        [concept()],
        operations=[
            {
                "id": "op.run",
                "name": "Run it",
                "definition": "Execute the script in the fixed environment.",
                "acts_on_concept_refs": ["concept.runtime"],
                "common_failures": ["wrong interpreter"],
            }
        ],
    )
    if bound:
        payload["stages"][0]["operation_refs"] = ["op.run"]
    assert (CONCEPT_UNUSED in codes(payload)) is not bound


@pytest.mark.asyncio
async def test_unused_concepts_are_reported_for_structural_review_not_sent_to_text_repair():
    from app.harness.context import HarnessContext
    from app.harness.schemas import TARGETED_REPAIR_CODES
    from app.harness.steps.h110_refine import RefineStep

    payload = artifact([concept()])
    ctx = HarnessContext(run_id="r", project_id="p", input={}, settings={})
    ctx.artifact = payload
    ctx.critic_report = {"severity": "major", "issues": concept_frame_failures(payload)}

    class NoCalls:
        async def complete_structured(self, **kwargs):
            pytest.fail("A text-only refiner cannot repair concept bindings")

    result = await RefineStep().execute(ctx, NoCalls())
    assert CONCEPT_UNUSED not in TARGETED_REPAIR_CODES
    assert result.metrics["manual_review"] == 1
    assert "structural review" in result.warnings[0]
    assert CONCEPT_UNUSED in codes(payload)


def test_a_broken_concept_frame_reaches_the_refiner_as_major():
    payload = artifact([concept(definition="d")], stage_concepts=["concept.runtime"])

    report = merged_report([], {"severity": "pass", "issues": []})

    assert report["severity"] == "pass", "a clean report must stay clean"
    issues = [item for item in concept_frame_failures(payload)]
    assert issues and issues[0]["code"] == CONCEPT_MISSING_EXPLANATION

    from app.harness.steps.critic_rules import check_artifact as heuristic_check

    raised = merged_report(heuristic_check(payload), {"severity": "pass", "issues": []})
    assert raised["severity"] == "major"


def test_concept_frame_failures_are_not_conflated_with_stage_content_gaps():
    """A concept defect names a Concept; it must not be reported as a Stage gap."""
    payload = artifact([concept(definition="d")], stage_concepts=["concept.runtime"])

    assert concept_frame_failures(payload)
    assert content_gate_failures(payload) == [], (
        "the stage is actionable; only the concept explains nothing"
    )


def test_the_codes_are_declared_so_renaming_one_breaks_a_test():
    from app.domain import quality

    assert {
        CONCEPT_MISSING_EXPLANATION,
        CONCEPT_CIRCULAR_DEFINITION,
        CONCEPT_UNUSED,
    } <= CONCEPT_FRAME_CODES
    for code in CONCEPT_FRAME_CODES:
        assert any(value == code for value in vars(quality).values())


@pytest.mark.parametrize(
    "name",
    [
        "langchain-basic-cop.json",
        "communication-basics-cop.json",
        "reference-langchain-cop.json",
    ],
)
def test_shipped_authored_artifacts_do_not_regress_on_the_new_rule(name):
    """The rule must catch bad examples without rejecting the real samples."""
    payload = json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))

    assert concept_frame_failures(payload) == []
