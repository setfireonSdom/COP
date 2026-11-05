"""Operational completeness: is this COP actually usable by a learner?

Three levels, separated because they fail for different reasons and because
"the JSON is legal" has been mistaken for "the product works" too often here:

    L1 structural   the JSON is a valid COP and every reference resolves.
    L2 operational  a reader can act on it: every Stage has an example, every
                    executable Stage says how to do the thing, and setup Stages
                    say how to verify it worked.
    L3 learnable    the loop closes: Minimal Practice, checkpoint questions,
                    and somewhere to go next.

The reference LangChain artifact passed the JSON Schema check for its entire
life while telling a reader nothing executable: 22 Stages, 0 examples, 0
implementation details, 12 Operations with no failure modes. A schema
validator cannot see that, because all of it is legal.

Every issue carries a stable `code`, the exact `entity_ref` it belongs to, and
a `recommended_change`. Stable codes matter because they are the contract the
critic, the refiner, the publish gate, and the tests all speak; free-text
critic output cannot be asserted on.

`known_source_ids` is optional on purpose. A caller holding the project's
sources passes them and gets orphan-reference detection; a caller that has no
idea what sources exist (a unit test on a bare fixture) gets everything else
rather than a flood of false "unresolvable" reports.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

L1 = "L1"
L2 = "L2"
L3 = "L3"
LEVELS = (L1, L2, L3)

# --- L1 codes ---------------------------------------------------------------
DANGLING_REF = "DANGLING_REF"
ORPHAN_EVIDENCE_REF = "ORPHAN_EVIDENCE_REF"
DUPLICATE_ENTITY_ID = "DUPLICATE_ENTITY_ID"
# The concept frame is the load-bearing structure of a COP: if a definition is a
# label, restates its own name, or the concept is never used, the reader cannot
# reason with it. These are mechanical facts about the artifact, not judgments
# about whether the explanation is *correct* -- a model grading its own prose
# would agree with itself.
CONCEPT_MISSING_EXPLANATION = "CONCEPT_MISSING_EXPLANATION"
CONCEPT_MISSING_ROLE = "CONCEPT_MISSING_ROLE"
CONCEPT_CIRCULAR_DEFINITION = "CONCEPT_CIRCULAR_DEFINITION"
CONCEPT_UNUSED = "CONCEPT_UNUSED"

# --- L2 codes ---------------------------------------------------------------
MISSING_STAGE_EXAMPLE = "MISSING_STAGE_EXAMPLE"
MISSING_IMPLEMENTATION_DETAIL = "MISSING_IMPLEMENTATION_DETAIL"
IMPLEMENTATION_DETAIL_NOT_ACTIONABLE = "IMPLEMENTATION_DETAIL_NOT_ACTIONABLE"
SETUP_NOT_ACTIONABLE = "SETUP_NOT_ACTIONABLE"
MISSING_VALIDATION_STEP = "MISSING_VALIDATION_STEP"
OPERATION_WITHOUT_COMMON_FAILURES = "OPERATION_WITHOUT_COMMON_FAILURES"

# --- L3 codes ---------------------------------------------------------------
WEAK_PRACTICE = "WEAK_PRACTICE"
PRACTICE_WITHOUT_CHECKPOINT = "PRACTICE_WITHOUT_CHECKPOINT"
EMPTY_EXPANSION_MAP = "EMPTY_EXPANSION_MAP"

#: L2 findings that prevent a generated candidate being marked `completed`.
#: Publication still permits incomplete content with explicit warnings.
#: A Stage the learner cannot act on is not a smaller defect than a missing
#: one, so the gate is on presence, not on wording.
BLOCKING_CODES = frozenset(
    {
        MISSING_STAGE_EXAMPLE,
        MISSING_IMPLEMENTATION_DETAIL,
        IMPLEMENTATION_DETAIL_NOT_ACTIONABLE,
        SETUP_NOT_ACTIONABLE,
        MISSING_VALIDATION_STEP,
    }
)
#: Concept-frame defects that make the artifact structurally dishonest rather
#: than merely unfinished. These are kept separate from `BLOCKING_CODES` so a
#: candidate can still be produced and repaired, but a *publish* is reported
#: with them rather than silently accepting a glossary of empty labels.
CONCEPT_FRAME_CODES = frozenset(
    {
        CONCEPT_MISSING_EXPLANATION,
        CONCEPT_MISSING_ROLE,
        CONCEPT_CIRCULAR_DEFINITION,
        CONCEPT_UNUSED,
    }
)

#: Titles that mark a Stage as environment setup. These carry a higher bar:
#: a setup Stage that names no command and no way to check success leaves the
#: learner stuck at step one, which is the exact failure "Install LangChain"
#: was supposed to avoid.
SETUP_TOKENS = (
    "install",
    "setup",
    "set up",
    "configure",
    "configuration",
    "bootstrap",
    "scaffold",
    "environment",
    "prerequisite",
    "provision",
    "getting started",
    "安装",
    "配置",
    "环境",
)

COLLECTIONS: dict[str, str] = {
    "goals": "goal",
    "shared_foundations": "foundation",
    "main_processes": "process",
    "stages": "stage",
    "concepts": "concept",
    "operations": "operation",
    "branches": "branch",
    "practices": "practice",
}

#: `field -> target collection` for every `_ref` / `_refs` the schema defines.
#: Checked generically so a new field cannot quietly ship a broken reference.
REFERENCE_FIELDS: dict[str, str] = {
    "goal_ref": "goals",
    "prerequisite_goal_refs": "goals",
    "from_goal_ref": "goals",
    "concept_refs": "concepts",
    "related_concept_refs": "concepts",
    "acts_on_concept_refs": "concepts",
    "operation_refs": "operations",
    "key_operation_refs": "operations",
    "stage_refs": "stages",
    "parent_stage_ref": "stages",
    "parent_process_ref": "main_processes",
    "branch_refs": "branches",
    "practice_ref": "practices",
}


class QualityIssue:
    """One thing a learner would hit, tied to the entity that causes it."""

    __slots__ = ("code", "level", "entity_type", "entity_ref", "explanation", "recommended_change")

    def __init__(
        self,
        *,
        code: str,
        level: str,
        entity_type: str,
        entity_ref: str,
        explanation: str,
        recommended_change: str,
    ) -> None:
        self.code = code
        self.level = level
        self.entity_type = entity_type
        self.entity_ref = entity_ref
        self.explanation = explanation
        self.recommended_change = recommended_change

    @property
    def blocking(self) -> bool:
        return self.code in BLOCKING_CODES

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "level": self.level,
            "entity_type": self.entity_type,
            "entity_ref": self.entity_ref,
            "explanation": self.explanation,
            "recommended_change": self.recommended_change,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"QualityIssue({self.code}, {self.entity_type}={self.entity_ref})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QualityIssue):
            return NotImplemented
        return (self.code, self.entity_ref) == (other.code, other.entity_ref)

    def __hash__(self) -> int:
        return hash((self.code, self.entity_ref))


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


#: Words that carry no explanatory weight on their own. A definition made only of
#: these plus the Concept's name is a label, not an explanation.
_LABEL_FILLER = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "it",
        "this",
        "that",
        "of",
        "for",
        "to",
        "concept",
        "thing",
        "object",
        "term",
        "idea",
        "stuff",
        "something",
        "的",
        "是",
        "一个",
        "一种",
        "东西",
        "概念",
        "术语",
        "这个",
        "那个",
    }
)
_DEFINITION_PLACEHOLDERS = frozenset(
    {"d", "r", "x", "tbd", "todo", "placeholder", "待补充", "待完善", "暂无", "待定", "待填写"}
)


def _meaningful(text: str) -> str:
    """Lowercase alphanumerics/CJK only, so punctuation cannot pad a definition."""
    return "".join(char for char in text.lower() if char.isalnum() or "\u4e00" <= char <= "\u9fff")


def _is_circular(definition: str, name: str) -> bool:
    """True when the definition is the name, optionally with filler around it.

    A definition may legitimately *mention* its own name ("Encoding turns
    thoughts into communication") -- that is an explanation. It is circular only
    when removing the name leaves nothing but filler behind.
    """
    # Preserve English word boundaries. Joining words first turns "is the"
    # into "isthe", which is no longer recognisable as filler.
    core = _tokens(definition.casefold())
    label = _tokens(name.casefold())
    if not core or not label:
        return False
    found_label = False
    remainder: list[str] = []
    index = 0
    while index < len(core):
        if core[index : index + len(label)] == label:
            found_label = True
            index += len(label)
            continue
        remainder.append(core[index])
        index += 1
    return found_label and _only_filler(remainder)


def _only_filler(tokens: list[str]) -> bool:
    filler = sorted((_tokens(word) for word in _LABEL_FILLER), key=len, reverse=True)
    index = 0
    while index < len(tokens):
        match = next((part for part in filler if tokens[index : index + len(part)] == part), None)
        if match is None:
            return False
        index += len(match)
    return True


def _is_placeholder(definition: str) -> bool:
    """Detect explicit placeholders, never infer explanatory value from length."""
    core = _meaningful(definition)
    return (
        not core
        or core in _DEFINITION_PLACEHOLDERS
        or (set(core) == {"x"})
        or _only_filler(_tokens(definition.casefold()))
    )


def _tokens(value: str) -> list[str]:
    """Split on script boundaries so English and Chinese both tokenize usefully."""
    tokens: list[str] = []
    current = ""
    for char in value:
        if "\u4e00" <= char <= "\u9fff":
            if current:
                tokens.append(current)
                current = ""
            tokens.append(char)
        elif char.isalnum():
            current += char
        else:
            if current:
                tokens.append(current)
                current = ""
    if current:
        tokens.append(current)
    return tokens


def _nonempty(value: Any) -> bool:
    """A string, or a container holding at least one non-blank entry."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_nonempty(item) for item in value.values())
    if isinstance(value, Sequence):
        return any(_nonempty(item) for item in value)
    return bool(value)


def is_setup_stage(stage: Mapping[str, Any]) -> bool:
    haystack = " ".join(
        _text(stage.get(field)) for field in ("title", "local_goal", "why_it_exists")
    ).lower()
    return any(token in haystack for token in SETUP_TOKENS)


def is_executable_stage(stage: Mapping[str, Any]) -> bool:
    """A Stage is executable when it asks the learner to do something.

    Operation references are the signal: a Stage that only names Concepts is a
    reading step, and demanding an implementation detail of it would push the
    model to invent busywork.
    """
    return bool(stage.get("operation_refs"))


def _detail_action(detail: Mapping[str, Any]) -> str:
    for field in ("action", "description", "steps", "summary"):
        if _nonempty(detail.get(field)):
            return _text(detail.get(field))
    return ""


def _detail_command(detail: Mapping[str, Any]) -> str:
    for field in ("command", "code", "snippet", "code_block"):
        if _nonempty(detail.get(field)):
            return _text(detail.get(field))
    return ""


def _detail_validation(detail: Mapping[str, Any]) -> str:
    for field in ("expected_result", "validation", "verify", "expected_output"):
        if _nonempty(detail.get(field)):
            return _text(detail.get(field))
    return ""


def detail_is_actionable(detail: Mapping[str, Any]) -> bool:
    return bool(_text(detail.get("title"))) and bool(
        _detail_action(detail) or _detail_command(detail)
    )


def _issue(
    code: str, level: str, entity_type: str, entity_ref: str, why: str, fix: str
) -> QualityIssue:
    return QualityIssue(
        code=code,
        level=level,
        entity_type=entity_type,
        entity_ref=entity_ref,
        explanation=why,
        recommended_change=fix,
    )


def _check_duplicate_ids(artifact: Mapping[str, Any]) -> list[QualityIssue]:
    """Duplicate ids make every other reference check ambiguous.

    Two Stages sharing an id is not cosmetic: the ref from a Main Process then
    resolves to whichever one happened to come first, and a learner's progress
    row silently attaches to the wrong Stage.
    """
    issues: list[QualityIssue] = []
    for collection, entity_type in COLLECTIONS.items():
        seen: set[str] = set()
        duplicates: set[str] = set()
        for entity in artifact.get(collection) or []:
            if not isinstance(entity, Mapping):
                continue
            entity_id = str(entity.get("id", ""))
            if not entity_id:
                issues.append(
                    _issue(
                        DUPLICATE_ENTITY_ID,
                        L1,
                        entity_type,
                        "",
                        f"A {entity_type} in {collection} has no id, so nothing can reference it.",
                        f"Give every {entity_type} a stable id.",
                    )
                )
            elif entity_id in seen:
                duplicates.add(entity_id)
            else:
                seen.add(entity_id)
        for entity_id in sorted(duplicates):
            issues.append(
                _issue(
                    DUPLICATE_ENTITY_ID,
                    L1,
                    entity_type,
                    entity_id,
                    f"Id '{entity_id}' appears more than once in {collection}, so references "
                    f"to it are ambiguous.",
                    f"Give each {entity_type} a distinct id.",
                )
            )
    return issues


def _check_references(
    artifact: Mapping[str, Any], known_source_ids: set[str] | None
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    ids: dict[str, set[str]] = {
        collection: {
            str(item.get("id")) for item in artifact.get(collection) or [] if item.get("id")
        }
        for collection in COLLECTIONS
    }

    for collection, entity_type in COLLECTIONS.items():
        for entity in artifact.get(collection) or []:
            if not isinstance(entity, Mapping):
                continue
            entity_id = str(entity.get("id", ""))
            for field, target in REFERENCE_FIELDS.items():
                if field not in entity:
                    continue
                raw = entity.get(field)
                values = [raw] if isinstance(raw, str) else [str(item) for item in raw or []]
                for value in values:
                    if value and value not in ids.get(target, set()):
                        issues.append(
                            _issue(
                                DANGLING_REF,
                                L1,
                                entity_type,
                                entity_id,
                                f"{collection}[{entity_id}].{field} points at '{value}', "
                                f"which is not in {target}.",
                                f"Remove '{value}' from {field}, or restore the "
                                f"missing {target} entity.",
                            )
                        )

    if known_source_ids is None:
        return issues

    for collection in ("goals", "stages"):
        for entity in artifact.get(collection) or []:
            if not isinstance(entity, Mapping):
                continue
            entity_id = str(entity.get("id", ""))
            for ref in entity.get("evidence_refs") or []:
                if not isinstance(ref, Mapping):
                    continue
                source_id = _text(ref.get("source_id"))
                if not source_id or source_id in known_source_ids:
                    continue
                issues.append(
                    _issue(
                        ORPHAN_EVIDENCE_REF,
                        L1,
                        COLLECTIONS[collection],
                        entity_id,
                        f"evidence_ref points at source '{source_id}', which this project "
                        f"does not have.",
                        f"Attach a real Source or drop the reference to '{source_id}'.",
                    )
                )
    return issues


def _check_concepts(artifact: Mapping[str, Any]) -> list[QualityIssue]:
    """Mechanical checks on the concept frame, not on whether prose is correct.

    A Concept is load-bearing: a Stage says "do X because of C", so a reader who
    cannot state C cannot follow the route. Three defects are objectively
    detectable, and each one has been shipped by real models:

    - a definition that is a placeholder or only a label,
    - a definition that restates the name (or is the name plus a stop word),
    - a Concept that no Stage and no Operation actually uses.

    Deliberately no semantic scoring here. "Is this definition *right*" needs a
    source check, which no string comparison can perform; pretending otherwise
    would recreate the failure this check exists to catch.
    """
    issues: list[QualityIssue] = []
    concepts = [c for c in artifact.get("concepts") or [] if isinstance(c, Mapping)]
    if not concepts:
        return issues

    used: set[str] = set()
    used_operations: set[str] = set()
    for stage in artifact.get("stages") or []:
        if isinstance(stage, Mapping):
            used.update(str(ref) for ref in stage.get("concept_refs") or [])
            used_operations.update(str(ref) for ref in stage.get("operation_refs") or [])
    for operation in artifact.get("operations") or []:
        if isinstance(operation, Mapping) and str(operation.get("id")) in used_operations:
            used.update(str(ref) for ref in operation.get("acts_on_concept_refs") or [])
    # `related_concept_refs` deliberately does NOT count as use. A cluster of
    # Concepts that only point at each other is still a glossary nobody acts on,
    # and accepting it would let the exact failure this check exists for pass.

    for concept in concepts:
        concept_id = str(concept.get("id", ""))
        name = _text(concept.get("name")) or concept_id
        definition = _text(concept.get("definition"))
        role = _text(concept.get("role"))

        # Circular first: it is the more specific diagnosis, and a short
        # label-style definition ("Runtime") is both short and circular. Telling
        # the repairer "add more words" would produce padding; "explain it" is
        # the correction that actually helps.
        if definition and _is_circular(definition, name):
            issues.append(
                _issue(
                    CONCEPT_CIRCULAR_DEFINITION,
                    L1,
                    "concept",
                    concept_id,
                    f"Concept '{name}' is defined by its own name, so the definition adds "
                    f"nothing a reader did not already see in the title.",
                    "Replace the label with an explanation: what it is, what it is not, or "
                    "what becomes possible when it is present.",
                )
            )
        elif _is_placeholder(definition):
            issues.append(
                _issue(
                    CONCEPT_MISSING_EXPLANATION,
                    L1,
                    "concept",
                    concept_id,
                    f"Concept '{name}' has an empty or explicit placeholder definition.",
                    "Explain in plain language what this thing is and what it does, so a "
                    "reader can use it before seeing the name again.",
                )
            )
        if not role:
            issues.append(
                _issue(
                    CONCEPT_MISSING_ROLE,
                    L1,
                    "concept",
                    concept_id,
                    f"Concept '{name}' states no role, so the reader cannot tell which "
                    f"part of the route depends on it.",
                    "Say where this Concept is needed and what a later action would get "
                    "wrong without it.",
                )
            )

        if concept_id and concept_id not in used:
            issues.append(
                _issue(
                    CONCEPT_UNUSED,
                    L1,
                    "concept",
                    concept_id,
                    f"Concept '{name}' is declared but no Stage or Stage-bound Operation uses it.",
                    "Regenerate the concept frame with Stage bindings, or review the unused "
                    "Concept manually. Text-only repair cannot change references or remove it.",
                )
            )
    return issues


def _check_stages(artifact: Mapping[str, Any]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for stage in artifact.get("stages") or []:
        if not isinstance(stage, Mapping):
            continue
        stage_id = str(stage.get("id", ""))
        title = _text(stage.get("title")) or stage_id

        example = stage.get("example")
        if not _nonempty(example):
            issues.append(
                _issue(
                    MISSING_STAGE_EXAMPLE,
                    L2,
                    "stage",
                    stage_id,
                    f"Stage '{title}' has no example, so a reader never sees the result "
                    f"they are working towards.",
                    "Add an example showing real input and the real output for this Stage.",
                )
            )

        if not is_executable_stage(stage):
            continue

        details = [d for d in stage.get("implementation_details") or [] if isinstance(d, Mapping)]
        if not details:
            issues.append(
                _issue(
                    MISSING_IMPLEMENTATION_DETAIL,
                    L2,
                    "stage",
                    stage_id,
                    f"Stage '{title}' asks the learner to perform Operations but gives no "
                    f"implementation detail to follow.",
                    "Add at least one implementation detail with a concrete action.",
                )
            )
            continue

        if not any(detail_is_actionable(detail) for detail in details):
            issues.append(
                _issue(
                    IMPLEMENTATION_DETAIL_NOT_ACTIONABLE,
                    L2,
                    "stage",
                    stage_id,
                    f"Stage '{title}' has implementation details, but none state a title and "
                    f"an action or a command.",
                    "Give each detail a title plus an action or a command a reader can run.",
                )
            )

        if is_setup_stage(stage) and not any(_detail_command(detail) for detail in details):
            issues.append(
                _issue(
                    SETUP_NOT_ACTIONABLE,
                    L2,
                    "stage",
                    stage_id,
                    f"Setup Stage '{title}' has no concrete command, so the learner cannot "
                    f"complete their environment from this page.",
                    "Add the exact install or configuration command, and where it runs.",
                )
            )

        if not any(_detail_validation(detail) for detail in details):
            issues.append(
                _issue(
                    MISSING_VALIDATION_STEP,
                    L2,
                    "stage",
                    stage_id,
                    f"Stage '{title}' has no expected result, so a reader cannot tell whether "
                    f"the step actually worked.",
                    "Add the expected output, or a command that proves the step succeeded.",
                )
            )
    return issues


def _check_operations(artifact: Mapping[str, Any]) -> list[QualityIssue]:
    return [
        _issue(
            OPERATION_WITHOUT_COMMON_FAILURES,
            L2,
            "operation",
            str(operation.get("id", "")),
            f"Operation '{_text(operation.get('name')) or operation.get('id')}' lists no common "
            f"failure, so a reader hitting one has nowhere to look.",
            "List the failures a beginner actually hits, and what to do about each.",
        )
        for operation in artifact.get("operations") or []
        if isinstance(operation, Mapping) and not _nonempty(operation.get("common_failures"))
    ]


def _check_learning_layer(artifact: Mapping[str, Any]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    practices = [p for p in artifact.get("practices") or [] if isinstance(p, Mapping)]
    if not practices:
        issues.append(
            _issue(
                WEAK_PRACTICE,
                L3,
                "artifact",
                str(artifact.get("artifact_id", "artifact")),
                "No Minimal Practice is attached, so the COP cannot be exercised.",
                "Add one practice that traverses a full Main Process.",
            )
        )
    for practice in practices:
        if not _nonempty(practice.get("checkpoint_questions")):
            issues.append(
                _issue(
                    PRACTICE_WITHOUT_CHECKPOINT,
                    L3,
                    "practice",
                    str(practice.get("id", "")),
                    f"Practice '{_text(practice.get('title')) or practice.get('id')}' has no "
                    f"checkpoint question, so completion is unverified.",
                    "Add at least one question that proves the practice was actually done.",
                )
            )
    if len(artifact.get("expansion_map") or []) < 2:
        issues.append(
            _issue(
                EMPTY_EXPANSION_MAP,
                L3,
                "artifact",
                str(artifact.get("artifact_id", "artifact")),
                "The Expansion Map has fewer than two directions, so the learner has no next step.",
                "Add at least two expansion directions beyond the current COP.",
            )
        )
    return issues


def check_artifact(
    artifact: Mapping[str, Any],
    *,
    known_source_ids: Iterable[str] | None = None,
    levels: Sequence[str] = LEVELS,
) -> list[QualityIssue]:
    """Report everything a learner would trip on, ordered by level then entity.

    `known_source_ids=None` skips orphan-reference detection rather than
    reporting every reference as unresolvable.
    """
    found: list[QualityIssue] = []
    wanted = set(levels)

    if L1 in wanted:
        found.extend(_check_duplicate_ids(artifact))
        found.extend(
            _check_references(artifact, None if known_source_ids is None else set(known_source_ids))
        )
        found.extend(_check_concepts(artifact))
    if L2 in wanted:
        found.extend(_check_stages(artifact))
        found.extend(_check_operations(artifact))
    if L3 in wanted:
        found.extend(_check_learning_layer(artifact))

    found.sort(key=lambda issue: (issue.level, issue.code, issue.entity_ref))
    return found


def blocking_issues(issues: Iterable[QualityIssue]) -> list[QualityIssue]:
    return [issue for issue in issues if issue.blocking]


def concept_frame_issues(artifact: Mapping[str, Any]) -> list[QualityIssue]:
    """Shared domain policy for generation and publication; no harness dependency."""
    return [
        issue
        for issue in check_artifact(artifact, levels=[L1])
        if issue.code in CONCEPT_FRAME_CODES
    ]


def completeness_summary(
    artifact: Mapping[str, Any],
    *,
    known_source_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Counts a test or an API can assert on without string-matching issues."""
    issues = check_artifact(artifact, known_source_ids=known_source_ids)
    stages = [s for s in artifact.get("stages") or [] if isinstance(s, Mapping)]
    executable = [s for s in stages if is_executable_stage(s)]
    with_example = [s for s in stages if _nonempty(s.get("example"))]
    with_detail = [s for s in executable if s.get("implementation_details")]
    operations = [o for o in artifact.get("operations") or [] if isinstance(o, Mapping)]
    with_failures = [o for o in operations if _nonempty(o.get("common_failures"))]
    refs = [
        ref
        for collection in ("goals", "stages")
        for entity in artifact.get(collection) or []
        if isinstance(entity, Mapping)
        for ref in entity.get("evidence_refs") or []
        if isinstance(ref, Mapping) and _text(ref.get("source_id"))
    ]
    # A citation with no quote says only *that* the entity was sourced. One with
    # a quote or a segment says what the source actually said, which is the
    # difference between a link and a checkable claim. Reported as a number
    # rather than as a blocking issue: an unquoted citation is weaker, not wrong,
    # and refusing to publish over it would strand artifacts still worth reading.
    anchored = [ref for ref in refs if _text(ref.get("quote_hint")) or _text(ref.get("segment_id"))]
    quoted = [ref for ref in refs if _text(ref.get("quote_hint"))]
    return {
        "levels": {
            level: {
                "issues": sum(1 for issue in issues if issue.level == level),
                "clean": not any(issue.level == level for issue in issues),
            }
            for level in LEVELS
        },
        "counts": {
            "stages": len(stages),
            "executable_stages": len(executable),
            "stages_with_example": len(with_example),
            "executable_stages_with_detail": len(with_detail),
            "operations": len(operations),
            "operations_with_common_failures": len(with_failures),
            "practices": len(artifact.get("practices") or []),
        },
        "coverage": {
            "stage_example": _ratio(len(with_example), len(stages)),
            "implementation_detail": _ratio(len(with_detail), len(executable)),
            "operation_common_failures": _ratio(len(with_failures), len(operations)),
            "evidence_anchored": _ratio(len(anchored), len(refs)),
        },
        "evidence": {
            "refs": len(refs),
            # Refs that point at something but do not narrow it down. Distinct
            # from `anchored`: a named segment says *where* in the source, a
            # quote says *what* it said. Only the second lets a reader check a
            # claim without opening the source and hunting for it.
            "refs_without_an_anchor": len(refs) - len(anchored),
            "refs_without_a_quote": len(refs) - len(quoted),
        },
        "orphan_evidence_refs": sum(1 for issue in issues if issue.code == ORPHAN_EVIDENCE_REF),
        "blocking": len(blocking_issues(issues)),
        "issues": [issue.as_dict() for issue in issues],
    }


def _ratio(numerator: int, denominator: int) -> float:
    """1.0 for an empty requirement: nothing to cover is not a coverage failure."""
    if denominator == 0:
        return 1.0
    return round(numerator / denominator, 4)
