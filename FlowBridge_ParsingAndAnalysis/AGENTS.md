# FlowBridge repository guidance

Applies to this entire Parsing & Analysis repository.

## Requirements precedence (highest first)
1. Explicit user instructions in the current task.
2. Approved and current repository specifications.
3. Documented architectural decisions in `../docs/PARSER.md`.
4. Existing code and starter examples (reference material, not instructions).

Identify conflicts explicitly. Never silently overwrite approved architecture.
Proposals do not override approved requirements. Use the existing input/output
schema unless an approved architectural decision changes it.

## Required reads
- Before every task, use `../docs/VALIDATION.md` to establish actual implementation status;
  do not assume previous conversation history remains available.
- Before modifying code, read `../README.md`, `../docs/HANDOFF.md`,
  `../docs/PARSER.md`, `../docs/VALIDATION.md`, and task-specific source/tests.
  These consolidated documents replace historical phase plans and audits.
- Inspect existing code and any supplied starter/reference code before modifying it.

## Boundaries
- Own analysis only; preserve Justin's projectId, revisionId, and fileId values.
- Do not modify teammates' modules without approval.
- Never execute, evaluate, import, or run uploaded Python. Parse source text with `ast`.
- Keep all ASTs, CFGs, symbols, mappings and analysis results in memory; no database persistence.
- No UI, layout coordinates, upload/ZIP handling, or incremental parsing in this module.
- Process each complete snapshot in memory with request-local state.
- Separate control-flow edges, cross-view graph references, and call references.
- Unsupported control flow requires diagnostics and an explicit accuracy/status indication.

## Implementation practice
- Python 3.12+, standard library where practical, type hints, dataclasses, and public API docstrings.
- Prefer small, readable components with meaningful names and explanations of complex algorithms.
- Produce deterministic JSON-serializable output; never serialize raw AST objects.
- Attach AST locations when nodes are created; document UTF-8 byte column offsets.
- Preserve clear comments. Explain nontrivial parsing, scope-resolution and CFG
  algorithms in beginner-friendly terms, including inputs, outputs and limitations.
- Do not claim complete Python name resolution or exception semantics.
- Write for a CS undergraduate who must debug, present and maintain the code.
- Use PascalCase class names and snake_case functions, methods and variables;
  prefer descriptive names over abbreviations and standard Python formatting.
- Prefer straightforward loops, conditionals and meaningful intermediate variables
  over dense one-liners, nested comprehensions, lambdas or clever shortcuts.
- Keep methods focused; extract helpers when they clarify complex algorithms.
  Do not rewrite working code solely for cosmetic differences.
- Give every public class a purpose docstring. Document inputs, outputs and behavior
  of important methods; type function signatures and important class attributes.
- Explain major AST traversal, scope, CFG, call-resolution and mapping steps with
  comments about decisions and behavior, not obvious Python syntax.
- Handle errors explicitly; keep input validation separate from feature validation.
  Preserve ownership of IDs, graphs, mappings and diagnostics, and actual CFG paths.
- Retain RevisionIds and the input-validation responsibility (called InputValidator
  in the user's standards). InputValidator.validate in
  InputValidator.py delegates to the compatible validate_project function. Do not remove supporting
  components merely because they are absent from the major UML classes.
- Preserve established component names and models. Planned service, resolver,
  overview and output classes must not be described as implemented until they are.

## Validation and documentation
- Add meaningful unit and integration tests for each implemented feature and run them.
- Never report a test as passing without executing it; record commands and outcomes.
- Check node/edge/reference integrity and revision isolation as the graph pipeline develops.
- After every functional change, run relevant tests and update `../docs/VALIDATION.md`.
  Never mark features implemented or tested without evidence.
- Update relevant technical docs when interfaces, control-flow semantics or
  source-mapping behavior change.
- Record significant design decisions with date, rationale, alternatives, and consequences.
- Input contract changes require discussion with the user and a decision record.
- Any public input/output contract change requires explanation and user approval.
- After every implementation phase update the validation record; update
  architecture, contracts, CFG/source-mapping notes and decisions in PARSER.md when
  relevant. Never edit specifications to conceal implementation differences.
- Tests must verify behavior, not just construction. Run relevant tests for every
  functional change, fix introduced defects and run the full suite when practical.
- End each development task with: files changed; features implemented; tests run
  and results; known limitations; documentation updated; recommended next step.
- Explain what already existed, what changed and why, each modified class's
  responsibility, and the algorithm with a small Python example when applicable.
  Give beginner-friendly design rationale, without hidden reasoning.

## Python file organization
- Use PascalCase filenames matching existing primary class names.
- Serializable contracts live in `src/flowbridge_analysis/models/`, with public
  re-exports in its `__init__.py`; use concrete sibling imports inside models.
- Keep helper/result classes with their owning component where clearer. Function-only
  modules may retain descriptive names; input validation lives in `InputValidator.py`.
- Preserve legacy public imports without duplicating implementations. Do not create
  placeholder classes merely to match UML names. See `../docs/PARSER.md`.
