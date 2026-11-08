# Phased implementation plan

Current status: bounded analysis, full-snapshot reanalysis, file execution views,
and diagram/source integration are verified with 284 parser tests. The shared
backend, UI tests, and browser flow checks are described in the root validation
record. Original numbering below differs from the later user phase sequence.
Remaining work includes intended-user validation, resource/process limits, and
broader compiler semantics. Dated milestones preserve historical evidence.

## Original Phase 0 — documentation baseline (historical, complete)
Acceptance: inspect available files; create AGENTS plus all ten required docs;
record missing starter code, requirements, proposed defaults and implementation
gaps; recommend a next task and stop. No Python rewrite or feature implementation.

## Phase 1 — input validation and package foundation (complete)
Depends on phase 0. Add pyproject.toml (Python >=3.12), src package, input/diagnostic
dataclasses, and JSON validation only. Confirm provisional validation defaults
against the unchanged required shape before implementation.
Acceptance: supplied example validates and preserves IDs; missing fields, wrong
types, bool revision, malformed JSON and duplicate file IDs yield structured
diagnostics; empty files/projects behave as documented; JSON roundtrip succeeds.
Use unittest, with no third-party runtime dependency. Do not add CFG stubs presented
as working features. Deliver tests and exact execution results.

## Phase 2 — parser and feature diagnostics (complete for initial subset)
Depends on phase 1. Add PythonParser and FeatureValidator, plus isolated file results.
Acceptance: valid/empty source parses; syntax errors and invalid edits do not crash;
one bad file does not suppress valid siblings; unsupported scopes are identified;
source text is never executed/imported. Normalize and test diagnostic locations.

## Phase 3 — metadata and lexical symbols (complete for documented subset)
Depends on phase 2. Extract functions, qualified names, all parameter kinds, spans,
scope IDs, local bindings and import bindings. Record module-level code explicitly.
Acceptance: zero/multiple parameters, duplicate definitions, shadowed names,
Unicode spans, and module/function scope separation have tests. Nested functions
and classes remain explicitly unsupported until designed.

## Phase 4 — sequential and branching CFGs (complete)
Depends on phase 3. Implement statements, Start/End, if/elif/else and return.
Acceptance: deterministic IDs, nested merges, early returns and unreachable code
tests pass; no edge leaves a return toward a following statement; all endpoints
exist; every source-backed node has accurate mappings. Diagnose loops until phase 5.

## Phase 5 — loops (complete for documented subset)
Depends on phase 4. Implement for/while and nearest-context break/continue.
Acceptance: back/exit edges, zero-iteration paths, nested loops and early returns
pass dedicated tests. Loop-else exhaustion/break distinction is now implemented
and tested by requested Phase 5B; lexical loop-else extraction remains incomplete.

## Phase 6 — overview graphs and canonical outputs (implemented)
Depends on phase 4; integrate phase 5 when available. Add ProjectGraphBuilder,
orchestration around the existing ProjectAnalysis model, and the two output projections.
Acceptance: project/file/function views, status propagation, empty projects/files,
all reference/mapping integrity checks, JSON serialization, identical downstream
IDs, and fresh-state reanalysis tests pass. Finalize analyze_file/result diagnostics
interfaces before advertising them.

## Phase 7 — same-file call resolution (bounded subset implemented)
Depends on phases 3 and 6. Resolve only unshadowed, statically identifiable direct
calls; distinguish unresolved, ambiguous, builtin and external calls.
Acceptance: recursion, forward declarations, duplicate definitions, parameter/local
shadowing and module-level calls are tested; no name-only project-wide guessing.
Decorated/rebound functions are not resolved without explicit supporting analysis.

## Phase 8 — bounded cross-file resolution (implemented)
Depends on phase 7. Proposed initial subset: unique root-relative modules and
absolute `import module [as alias]` / `from module import name [as alias]` bindings.
No relative/star imports, dynamic imports, re-exports or runtime sys.path inference.
Acceptance: aliases resolve only through known unshadowed bindings; ambiguous
module paths and missing targets stay nonresolved; no user code is imported.
Document supported path conventions before enabling this subset.

## Phase 9 — basic try/except (bounded subset integrated)
Depends on phases 5 and 6. Implement the bounded CFG_DESIGN subset and label its
conservative semantics. Acceptance: normal bypass, possible handler entry,
unhandled exits, return-expression exceptions and handler errors have tests;
unsupported else/finally/nesting produce diagnostics, not incorrect sequential CFGs.

## Phase 10 — integration hardening
Depends on phases 6–9. Add representative examples and teammate-facing JSON fixtures.
Acceptance: complete TESTING matrix, determinism, mixed-file errors, two revisions,
no stale mappings, and projection integrity pass on Python 3.12+. Set and test
resource limits before exposure to untrusted uploads (limits are currently undecided).

## Deferred work
Saved workspaces, databases, incremental parsing, richer Python semantics, class/
nested-function support, full exception typing and stable IDs across edits.
The supplied starter has now been statically inspected; see reference/README.md
for reusable ideas and gaps. It is inspiration only, not the active implementation.

## Structural refactoring complete — 2026-11-03
PascalCase component files and individual model files now match existing class
names. No pipeline phase or algorithm was added. Output classes remain phase 6
work. All 113 prior tests plus four import/identity tests pass (117 total).
See FILE_ORGANIZATION.md for migration details.

## Audit-driven task order — 2026-11-03
Phase 0 audit complete (ARCHITECTURE_AUDIT.md); 117 baseline tests passed.
Current requested Phase 1: InputValidator module/class compatibility plus ID
verification and scope documentation. Existing validation/ID algorithms already work.
Then split original phase 6 into: (6a) ProjectGraphBuilder overviews/navigation,
(6b) request-local service assembly/status/integrity, (6c) output projections.
ProjectAnalysis is implemented as a record; FlowchartOutput and MappingOutput are
not implemented records or adapters. Original phases 7–10 remain pending except
for the bounded phase 9 function CFG algorithm already implemented.

## Requested Phase 1 verification complete — 2026-11-03
InputValidator class/module naming and compatibility are implemented; existing
structural rules remain unchanged. RevisionIds keeps its established format with
explicit uniqueness/ownership documentation and broader tests. Full suite: 127 pass.
Do not repeat already working validation or ID generation in the service.
Next bounded task: 6a ProjectGraphBuilder only. Accept existing file/function
metadata and function graph identities; build project/file overview nodes and
GraphReferences without execution edges. Test empty/multiple files, ownership,
unsupported targets and deterministic IDs. Service/status integration and adapters
remain separate follow-up tasks; preserve incomplete lexical-analysis diagnostics.

## Requested Phase 2 — UML data model completion (complete, 2026-11-03)
This is the user's new model-completion phase, distinct from original phase 2
parsing. All nine existing models inspected; graphType and edge label implemented,
nested validation and reference integrity strengthened, serialization tested.
Focused model suite: 26 pass; full suite: 139 pass. Exact diagram comparison remains
limited to the supplied class list/field requirements because images are absent.
Next: original phase 6a ProjectGraphBuilder only. Preserve D019's graphType contract;
retain source-bound/scope/mapping-completeness work in integration hardening.

## Requested Phases 3/4 — parser/features and metadata (2026-11-03)
Completed for the documented subset, building on original phases 2/3. ParseResult
now includes file identity; feature traversal is named and stateless; ordinary
loop bindings/calls are extracted. Nested functions remain explicitly unsupported
with body isolation. Basic try/except feature/CFG support already existed and stays
conservative; try binding extraction remains incomplete. No CFG work performed.
151 tests pass. Keep remaining service/overview/output milestones separate from
this completion; next bounded implementation remains original phase 6a.

## Requested Phase 5A verification complete — 2026-11-03
Existing sequence/branch/return construction now has focused helpers and seven
additional exact-connectivity tests. No new loop work; existing loop and exception
regressions pass. Original phase 6a remains the next missing implementation.

## Requested Phase 5B complete — 2026-11-03
while/for, nested contexts, back/normal exits, break/continue and early return are
verified, with loop-else now implemented. 52 CFG / 170 total tests pass. Phase 5A
behavior is preserved. Broader loop-else lexical extraction is separate from this
CFG milestone. Next missing component remains original phase 6a ProjectGraphBuilder.

## Requested Phase 6 completed — 2026-11-03
CallResolver now implements bounded same-file and absolute cross-file resolution,
ahead of original overview/service phases at the user's request. See
CALL_RESOLUTION.md; 183 tests pass including exception subset regressions.
Next missing component: ProjectGraphBuilder, followed by service/output assembly.

## Requested Phases 7/8 complete — 2026-11-03
Hierarchy, service assembly and both projections are implemented and tested (194
passing tests). Sample outputs are generated from the real pipeline. Remaining work:
compiler-context/resource hardening, complete omitted lexical subtrees, consumer
integration, and separately approved broader Python semantics. No module CFG or
public relationship-field renaming was introduced.

## Current completion
Requested editing/review phases are complete for the documented subset; 207 tests
pass. Use FINAL_REVIEW.md and INTEGRATION_GUIDE.md for remaining hardening and team
consumption. Earlier dated phase entries above are historical, not current blockers.
