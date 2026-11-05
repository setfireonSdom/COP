"""JSON Schemas describing each Harness step's structured output.

These schemas are the contract between the LLM, the mock provider, and
validation. The `title` is also the routing key the mock provider uses to pick
a deterministic response, so titles must be unique and stable.
"""

from typing import Any

EVIDENCE_REF = {
    "type": "object",
    "properties": {
        "source_id": {"type": "string"},
        "segment_id": {"type": "string"},
        "quote_hint": {"type": "string"},
    },
    "required": ["source_id"],
    "additionalProperties": True,
}

# The one shape a Stage's method is allowed to take, shared by the H50 output
# schema, the canonical artifact schema, and the H110 refiner. Keeping a single
# definition here is what stops the three from drifting: a detail the generator
# can produce but the refiner cannot rewrite, or a published detail the schema
# would reject, is a dead end for the user.
IMPLEMENTATION_DETAIL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["title"],
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "action": {"type": "string"},
        "command": {"type": "string"},
        "expected_result": {"type": "string"},
        "caution": {"type": "string"},
    },
    "additionalProperties": True,
}

EXAMPLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["summary"],
    "properties": {
        "summary": {"type": "string", "minLength": 1},
        "input": {"type": "string"},
        "output": {"type": "string"},
        "note": {"type": "string"},
    },
    "additionalProperties": True,
}

INTAKE_SCHEMA: dict[str, Any] = {
    "title": "H00Intake",
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "scope_hint": {"type": "string"},
        "target_outcomes": {"type": "array", "items": {"type": "string"}},
        "learner_level": {"type": "string"},
        "language": {"type": "string"},
        "depth": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["topic", "target_outcomes", "learner_level", "language", "depth"],
    "additionalProperties": True,
}

SCOPE_SCHEMA: dict[str, Any] = {
    "title": "H10ScopeResolution",
    "type": "object",
    "properties": {
        "domain": {"type": "string"},
        "scope": {"type": "string"},
        "target_user": {"type": "string"},
        "non_goals": {"type": "array", "items": {"type": "string"}},
        "ambiguity_notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["domain", "scope", "target_user"],
    "additionalProperties": True,
}

RESEARCH_BRIEF_SCHEMA: dict[str, Any] = {
    "title": "H20ResearchBrief",
    "type": "object",
    "properties": {
        "domain_purpose": {"type": "string"},
        "capability_candidates": {"type": "array", "items": {"type": "string"}},
        "workflow_candidates": {"type": "array", "items": {"type": "string"}},
        "structural_terms": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "string"}},
        "version_specific_facts": {"type": "array", "items": {"type": "string"}},
        "evidence_index": {"type": "array", "items": EVIDENCE_REF},
    },
    "required": ["domain_purpose", "capability_candidates", "workflow_candidates"],
    "additionalProperties": True,
}

GOALS_SCHEMA: dict[str, Any] = {
    "title": "H30GoalExtraction",
    "type": "object",
    "properties": {
        "goals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "outcome": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "prerequisite_goal_keys": {"type": "array", "items": {"type": "string"}},
                    "evidence_refs": {"type": "array", "items": EVIDENCE_REF},
                },
                "required": ["key", "title", "outcome"],
                "additionalProperties": True,
            },
        }
    },
    "required": ["goals"],
    "additionalProperties": True,
}

# Internal planning contract, persisted in process_drafts rather than added to
# the published COP schema. H50 realizes it in existing reader-facing fields.
TEACHING_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "central_question": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "why_this_order": {"type": "string", "minLength": 1, "pattern": r"\S"},
        "running_case": {
            "type": "object",
            "properties": {
                "scenario": {"type": "string", "minLength": 1, "pattern": r"\S"},
                "facts": {"type": "array", "items": {"type": "string", "pattern": r"\S"}},
                "hypotheses": {
                    "type": "array",
                    "items": {"type": "string", "pattern": r"\S"},
                },
            },
            "required": ["scenario", "facts", "hypotheses"],
            "additionalProperties": False,
        },
        "stages": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "stage_key": {"type": "string", "minLength": 1},
                    "learning_question": {"type": "string", "pattern": r"\S"},
                    "why_now": {"type": "string", "pattern": r"\S"},
                    "builds_on": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {"type": "string"},
                    },
                    "reasoning_moves": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "pattern": r"\S"},
                    },
                    "check_focus": {"type": "string", "pattern": r"\S"},
                    "next_gap": {"type": "string", "pattern": r"\S"},
                },
                "required": [
                    "stage_key",
                    "learning_question",
                    "why_now",
                    "builds_on",
                    "reasoning_moves",
                    "check_focus",
                    "next_gap",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["central_question", "why_this_order", "running_case", "stages"],
    "additionalProperties": False,
}

PROCESSES_SCHEMA: dict[str, Any] = {
    "title": "H40MainProcessConstruction",
    "type": "object",
    "properties": {
        "key": {"type": "string"},
        "title": {"type": "string"},
        "outcome": {"type": "string"},
        "teaching_plan": TEACHING_PLAN_SCHEMA,
        "stages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "local_outcome": {"type": "string"},
                },
                "required": ["key", "title", "local_outcome"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["key", "title", "outcome", "stages", "teaching_plan"],
    "additionalProperties": True,
}

STAGES_SCHEMA: dict[str, Any] = {
    "title": "H50StageEnrichment",
    "type": "object",
    "properties": {
        "stages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "local_goal": {"type": "string"},
                    "why_it_exists": {"type": "string"},
                    "local_outcome": {"type": "string"},
                    "dependency_notes": {"type": "array", "items": {"type": "string"}},
                    "concept_candidates": {"type": "array", "items": {"type": "string"}},
                    "operation_candidates": {"type": "array", "items": {"type": "string"}},
                    "implementation_detail_candidates": {
                        "type": "array",
                        "items": IMPLEMENTATION_DETAIL_SCHEMA,
                        "description": (
                            "At least one per Stage that asks for an Operation. Never empty."
                        ),
                    },
                    "example_candidate": EXAMPLE_SCHEMA,
                    "evidence_refs": {"type": "array", "items": EVIDENCE_REF},
                },
                "required": [
                    "key",
                    "local_goal",
                    "local_outcome",
                    "example_candidate",
                ],
                "additionalProperties": True,
            },
        }
    },
    "required": ["stages"],
    "additionalProperties": True,
}

CANONICALIZE_SCHEMA: dict[str, Any] = {
    "title": "H60CanonicalizeConceptsOperations",
    "type": "object",
    "properties": {
        "concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "name": {"type": "string"},
                    "definition": {"type": "string"},
                    "role": {"type": "string"},
                    "related_concept_keys": {"type": "array", "items": {"type": "string"}},
                    "key_operation_keys": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "name", "definition", "role"],
                "additionalProperties": True,
            },
        },
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "name": {"type": "string"},
                    "definition": {"type": "string"},
                    "purpose": {"type": "string"},
                    "acts_on_concept_keys": {"type": "array", "items": {"type": "string"}},
                    "common_failures": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "name", "definition"],
                "additionalProperties": True,
            },
        },
        "stage_bindings": {
            "type": "object",
            "description": "Maps stage key to the concept/operation keys it uses.",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "concept_keys": {"type": "array", "items": {"type": "string"}},
                    "operation_keys": {"type": "array", "items": {"type": "string"}},
                },
                "additionalProperties": True,
            },
        },
    },
    "required": ["concepts", "operations", "stage_bindings"],
    "additionalProperties": True,
}

COMPRESSION_SCHEMA: dict[str, Any] = {
    "title": "H70BranchFoundationCompression",
    "type": "object",
    "properties": {
        "alternative_branches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_stage_key": {"type": "string"},
                },
                "required": ["key", "title", "parent_stage_key"],
                "additionalProperties": True,
            },
        },
        "extension_branches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_process_key": {"type": "string"},
                },
                "required": ["key", "title", "parent_process_key"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["alternative_branches", "extension_branches"],
    "additionalProperties": True,
}

LEARNING_LAYER_SCHEMA: dict[str, Any] = {
    "title": "H80LearningLayer",
    "type": "object",
    "properties": {
        "mental_model": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "flow": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary"],
            "additionalProperties": True,
        },
        "practices": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "title": {"type": "string"},
                    "process_key": {"type": "string"},
                    "instructions": {"type": "array", "items": {"type": "string"}},
                    "expected_outcome": {"type": "string"},
                    "checkpoint_questions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "title", "process_key", "instructions", "expected_outcome"],
                "additionalProperties": True,
            },
        },
        "expansion_map": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "from_goal_key": {"type": "string"},
                },
                "required": ["title"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["mental_model", "practices", "expansion_map"],
    "additionalProperties": True,
}

CRITIC_SCHEMA: dict[str, Any] = {
    "title": "H100Critic",
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["pass", "minor", "major"]},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "entity_ref": {"type": "string"},
                    "explanation": {"type": "string"},
                    "recommended_change": {"type": "string"},
                },
                "required": ["code", "entity_ref", "explanation", "recommended_change"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["severity", "issues"],
    "additionalProperties": True,
}

CRITIC_ISSUE_CODES = (
    "GOAL_TOO_VAGUE",
    "PROCESS_MAINLINE_HIDDEN",
    "STAGE_TOO_BROAD",
    "CONCEPT_OVERPROMOTED",
    "OPERATION_TOO_LOW_LEVEL",
    "ENCYCLOPEDIA_DRIFT",
    "API_MANUAL_DRIFT",
    "OVERSIMPLIFIED",
    "MISSING_CORE_CONCEPT",
    "WEAK_PRACTICE",
    "UNSUPPORTED_SPECIFIC_CLAIM",
    # Content-contract codes. These are raised by the deterministic checker in
    # `app.domain.quality`, not by the model: whether a Stage carries an example
    # is a fact about the artifact, and a model asked to grade its own output on
    # this will agree with itself.
    "MISSING_STAGE_EXAMPLE",
    "MISSING_IMPLEMENTATION_DETAIL",
    "IMPLEMENTATION_DETAIL_NOT_ACTIONABLE",
    "SETUP_NOT_ACTIONABLE",
    "MISSING_VALIDATION_STEP",
    "OPERATION_WITHOUT_COMMON_FAILURES",
    # Concept-frame defects, raised by the same deterministic checker. A model
    # asked to review its own definitions tends to approve them; a string check
    # for a placeholder or a self-referential definition cannot.
    "CONCEPT_MISSING_EXPLANATION",
    "CONCEPT_MISSING_ROLE",
    "CONCEPT_CIRCULAR_DEFINITION",
    "CONCEPT_UNUSED",
    # Synthesised by H140 when the critic found nothing for the targeted entity.
    # Without it the mock would have no recognised issue to act on and a
    # refinement would silently propose nothing.
    "USER_REQUESTED_REFINEMENT",
)

#: Codes the refiner may act on. A model asked to repair "the artifact is too
#: long" rewrites whatever it likes; asked to repair
#: `MISSING_IMPLEMENTATION_DETAIL` on one Stage, it fills that Stage in.
TARGETED_REPAIR_CODES = frozenset(
    {
        "MISSING_STAGE_EXAMPLE",
        "MISSING_IMPLEMENTATION_DETAIL",
        "IMPLEMENTATION_DETAIL_NOT_ACTIONABLE",
        "SETUP_NOT_ACTIONABLE",
        "MISSING_VALIDATION_STEP",
        "OPERATION_WITHOUT_COMMON_FAILURES",
        "UNSUPPORTED_SPECIFIC_CLAIM",
        # Text-repairable concept-frame defects. CONCEPT_UNUSED is excluded:
        # repairing bindings/removing entities requires structural review.
        # The refiner is already allowed to rewrite
        # `definition`/`role`; without these codes it would be told about the
        # defect and never act on it. Bindings stay untouched, so a repair here
        # can explain a Concept but cannot silently drop it from a Stage.
        "CONCEPT_MISSING_EXPLANATION",
        "CONCEPT_MISSING_ROLE",
        "CONCEPT_CIRCULAR_DEFINITION",
        "USER_REQUESTED_REFINEMENT",
    }
)

# H120 asks for the whole artifact back, so the schema stays deliberately loose:
# the point of the step is to fix reported reference errors, and a strict schema
# would fail the response for reasons the repair prompt never asked about.
ARTIFACT_REPAIR_SCHEMA: dict[str, Any] = {
    "title": "H120RepairArtifact",
    "type": "object",
    "required": [
        "schema_version",
        "artifact_id",
        "domain",
        "mental_model",
        "goals",
        "shared_foundations",
        "main_processes",
        "stages",
        "concepts",
        "operations",
        "branches",
        "practices",
        "expansion_map",
        "metadata",
    ],
    "additionalProperties": True,
}

# Fields a refiner may rewrite. Anything else is structural and stays code-owned.
#
# `implementation_details`, `example`, and `common_failures` are refinable because
# the content gate reports them by name; a repair the refiner is not allowed to
# make would leave the user with a blocked publish and no way out. They are still
# leaf content, never references, so the structural boundary is unchanged.
REFINABLE_FIELDS: dict[str, frozenset[str]] = {
    "goal": frozenset({"title", "outcome", "why_it_matters"}),
    "process": frozenset({"title", "outcome"}),
    "stage": frozenset(
        {
            "title",
            "local_goal",
            "why_it_exists",
            "local_outcome",
            "example",
            "implementation_details",
        }
    ),
    "concept": frozenset({"name", "definition", "role"}),
    "operation": frozenset({"name", "definition", "purpose", "common_failures"}),
    "branch": frozenset({"title", "description"}),
}

# The only structured leaf values a refiner may replace. Reuse H50's shapes:
# generation and repair must agree on what a method or example looks like.
STRUCTURED_REVISION_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
    "stage": {
        "example": EXAMPLE_SCHEMA,
        "implementation_details": {
            "type": "array",
            "minItems": 1,
            "items": IMPLEMENTATION_DETAIL_SCHEMA,
        },
    },
    "operation": {
        "common_failures": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
    },
}
STRUCTURED_REFINABLE_FIELDS = {
    kind: frozenset(fields) for kind, fields in STRUCTURED_REVISION_SCHEMAS.items()
}
TEXT_REVISION_SCHEMA: dict[str, Any] = {"type": "string", "minLength": 1}


def revision_value_schema(entity_type: str, field: str) -> dict[str, Any]:
    """Shape only; authorization and user locks remain the applier's job."""
    return STRUCTURED_REVISION_SCHEMAS.get(entity_type, {}).get(field, TEXT_REVISION_SCHEMA)


def _refinement_schema(*, text_only: bool = False) -> dict[str, Any]:
    """Build a field-dependent value contract, not an untyped JSON escape hatch.

    Group plain text fields so the prompt stays compact. An object is valid for
    Stage.example, for instance, but not Goal.title or any structural reference.
    Both variants keep the existing mock routing key; H140's review UI still
    consumes text proposals, while H110 repairs canonical structured content.
    """
    variants: list[dict[str, Any]] = []
    for kind, fields in REFINABLE_FIELDS.items():
        structured = STRUCTURED_REVISION_SCHEMAS.get(kind, {})
        variants.append(
            {
                "properties": {
                    "entity_type": {"const": kind},
                    "field": {"enum": sorted(fields - structured.keys())},
                    "value": TEXT_REVISION_SCHEMA,
                }
            }
        )
        if not text_only:
            for field, value_schema in structured.items():
                variants.append(
                    {
                        "properties": {
                            "entity_type": {"const": kind},
                            "field": {"const": field},
                            "value": value_schema,
                        }
                    }
                )
    return {
        "title": "H110Refine",
        "type": "object",
        "properties": {
            "revisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "entity_type": {"type": "string", "enum": list(REFINABLE_FIELDS)},
                        "entity_key": {"type": "string", "minLength": 1},
                        "field": {"type": "string"},
                        "value": {"type": ["string", "array", "object"]},
                    },
                    "required": ["entity_type", "entity_key", "field", "value"],
                    "oneOf": variants,
                    "additionalProperties": True,
                },
            }
        },
        "required": ["revisions"],
        "additionalProperties": True,
    }


REFINE_SCHEMA = _refinement_schema()
TEXT_REFINE_SCHEMA = _refinement_schema(text_only=True)
