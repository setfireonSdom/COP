"""Reader-facing writing guidance, independent of storage and prompt payloads.

These rules influence future completions only. Presence/schema gates remain in
domain quality checks; semantic learnability is not established by a prompt.
"""

SCOPE_GUIDANCE = """Reader-facing scope:
- Use a short topic name, not a paragraph, for the Domain name.
- Start the scope with the concrete result the reader will work towards, then
  state the default approach, starting resources/skills, and exclusions.
- Distinguish building an implementation from deploying an existing product.
  If intent is ambiguous, state the chosen assumption and alternatives in the
  available scope/ambiguity fields; do not present the assumption as confirmed.
- Do not invent installed software, owned resources, credentials or prior work.
"""

GOAL_GUIDANCE = """Reader-facing goals:
- Name an observable capability or result using plain language and a concrete verb.
  Avoid methodology jargon such as intent capture, constraint convergence, or
  artifact handoff when a direct description of the task would be clearer.
- A planning document is a legitimate result when the user requested planning,
  research or writing. Otherwise do not substitute a stack of planning documents
  for the requested working capability; keep necessary preparation proportional.
- Keep goal titles short; put conditions and verification in the outcome.
"""

PROCESS_GUIDANCE = """Reader-facing route:
- Give one default route to the goal, not a menu of all approaches.
- Reuse the previous step's output as the next step's input, naming the same
  files, objects and configuration consistently across the route.
- Do not add a new intent-capture or requirements-writing stage at the start of
  every process when the scope already establishes those decisions.
- Include necessary prerequisites and safety checks, but avoid paperwork that
  does not change a later decision or help verify the requested capability.
- Plan a central learning question and one running case before expanding Stages.
  Explain why the reasoning needs this order; separate given facts, hypothetical
  example inputs and hypotheses. A later Stage must have a justified input from
  an earlier result, not just a plausible-sounding title.
"""

STAGE_GUIDANCE = """Reader-facing step:
- The reader must be able to answer: what am I doing, what do I need, what action
  do I take, what result should I get, how do I check it, and what if it fails?
- Use existing fields: local_goal for purpose, implementation actions for the
  default method and prerequisites, local_outcome for the deliverable,
  expected_result for an observable check, and caution for a failure sign and
  recovery action. Do not add undeclared fields or restate the same paragraph.
- Explain where placeholder values come from and which environment commands
  assume. Never invent credentials or make examples look like the user's data.
- Checks must inspect the task's result, not merely confirm that a note exists
  or a checklist was filled in, unless that document is the requested result.
- Do not force shell commands into conceptual, writing or decision tasks.
  Such tasks still need a concrete exercise or decision and a suitable check.
- Examples are hypothetical illustrations, not claims that work was executed.
  Do not claim the generated instructions or a learner's capability were tested.
- For a new learner, explain the causal chain from input to action to changed
  state to observable output. A list of commands is not an explanation.
- For a configuration-writing task, supply the complete minimal configuration or
  an accessible upstream artifact containing it, then explain essential fields
  and map every placeholder to its source. A validation command alone is not the
  method for writing that configuration.
- Use the same running task, filenames, values and environment across the worked
  example, instructions and check. Introduce one manageable change for practice,
  explaining how to predict its effect rather than merely copy a second example.
- Every introduced Concept needs a reason in this Stage's explanation, not just
  a name in a candidate list. Show observation → inference → limits in the worked
  case, including what supports the inference and what evidence would change it.
  Explain which unresolved question motivates the next Stage.
- For non-code learning, prefer a concrete comparison, prediction or reasoned
  decision and its check. Shell/grep and keyword spotting are not substitutes
  for semantic understanding; use tools only when the actual task needs them.
"""

CONCEPT_GUIDANCE = """Teach the Concepts, not just name them:
- In definition, explain what the object does in plain language, give a small
  concrete example, and distinguish the nearest easily confused object.
- Never define a Concept with its own name, a synonym of its name, or a
  placeholder like "a thing" / "the concept". The reader already saw the name;
  the definition must add what the name does not tell them.
- In role, explain why the learner needs it here and what later action depends
  on it. Use the Stage's action context to connect the object to its operation.
- Expanding an acronym into more acronyms is not an explanation. Do not use
  unexplained terminology as the definition of another unexplained term.
- Adapt depth to the declared learner. Keep necessary explanation complete;
  avoid encyclopedic history, unrelated variants, or arbitrary word-count padding.
- Explain where a model or abstraction is useful and where it stops fitting the
  observed case; never identify the abstraction with reality itself. Use only
  Concepts needed to support the reasoning, not a fixed concept count.
- Every Concept must be used: referenced by a Stage it supports or by a
  Stage-bound Operation that acts on it. A Concept that only cross-links other Concepts is
  a glossary entry, and it will be rejected.
"""

CRITIC_GUIDANCE = """Reader-facing review:
- Check that the scope declares the chosen approach and assumptions, rather than
  silently replacing implementation with installation (or vice versa).
- Use GOAL_TOO_VAGUE for abstract capability descriptions and
  PROCESS_MAINLINE_HIDDEN when unnecessary paperwork displaces the working route.
- Check action/result/check/recovery coherence, not merely field presence. A
  command that writes a planning note is not proof of a working deployed system.
- Use UNSUPPORTED_SPECIFIC_CLAIM when invented user resources, unverified example
  outputs or an undeclared assumption are presented as established facts.
- Do not reject necessary preparation or legitimate writing/research deliverables
  just because they produce documents. Judge them against the declared scope.
- Treat a missing input producer, missing default configuration, unexplained
  load-bearing concept, or a worked example inconsistent with the instructions
  as a major teaching defect. Identify the exact entity and broken transition;
  do not pass it merely because implementation_details contains a command.
- Use PROCESS_MAINLINE_HIDDEN for broken task handoffs and
  MISSING_IMPLEMENTATION_DETAIL for a missing default method (including a
  configuration-writing step that supplies only a validation command).
- Check actual misconceptions and logical jumps even when all fields are present:
  trace the case from observation through the stated inference to its limits.
  Is the warrant valid, is there a plausible alternative the claim ignores, does
  the check distinguish those alternatives, and can the next Stage use that
  result? A label match or a successful command does not prove understanding.
- Use OVERSIMPLIFIED for a false equivalence (including abstraction = reality),
  an invalid inference or a misleading causal explanation; MISSING_CORE_CONCEPT
  for an unexplained distinction on which the reasoning depends; and
  UNSUPPORTED_SPECIFIC_CLAIM for a hypothesis asserted as established fact.
  Name the exact entity, quote the faulty claim or identify the missing logical
  link, and recommend the corrected reasoning or a discriminating counterexample.
  Do not prescribe extra length or concept counts as a substitute for correction.
- In particular, read each Concept definition as if you did not know the term.
  A definition that is long but defines something other than how the term is
  used in this route is a conceptual error, not a style issue: report it with
  OVERSIMPLIFIED or MISSING_CORE_CONCEPT and name the Stage that relies on the
  wrong sense. Mechanical placeholder/circular/unused checks are handled in code.
- Judge semantic coherence from reader-visible fields, not an unseen teaching
  plan or the presence of planning labels. Do not claim instructional effectiveness
  or learner understanding has been empirically verified by this review.
"""
