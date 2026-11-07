# Testing

## Working standards update — 2026-11-03
Documentation-only update to AGENTS.md and PROGRESS.md, recorded here for clarity.
No tests added or executed for this update, and no Python files changed.
At that earlier documentation-only update, the latest suite was 117 passing tests.
See the Phases 9/10 execution section for current evidence.

## Current evidence
273 active unittest tests pass on Python 3.12.14. Coverage includes validation,
IDs, parsing, feature checks, metadata/symbols, calls, exact CFG connectivity,
hierarchy, models, projections and full-snapshot editing. See Phases 9/10 actual
execution results below for baseline failures and final verification. Earlier
milestone counts are historical. Starter tests remain unexecuted reference material.

November 6 integration review: `uv run python scripts/check_modules.py` from the
shared repository root passed 219 backend pytest cases and 273 parser unittest
cases (492 total). Parser discovery runs from its own folder. Backend Ruff and
source/wheel builds also passed. The existing Starlette/HTTPX deprecation warning
does not fail the backend suite.

The procedural update adds 51 parser cases. Three review regressions cover nested
module returns, unsafe resolution with omitted try bindings, and injected
function/module CFG failures in both file orders. The failure checks verify no
partial symbols, calls, mappings, or function graphs leak from the failed file.
Backend tests also check module graph/source lookup through file, ZIP, and mocked
GitHub imports with unchanged CRLF/tabs, encoding declarations, and revision IDs.

Executed from the repository root in PowerShell:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -v
```
Historical phase-5 result: `Ran 170 tests` / `OK`, zero failures or errors. No dependency installation
was needed. Tests cover fields, duplicate IDs/keys, missing references, source
coordinates, roundtrip, serialization, nonfinite JSON, isolation and deterministic IDs.

Parser/feature coverage now includes empty and valid functions, malformed and
indented source, NUL and unencodable text, UTF-8/CRLF coordinates, point/missing
locations, injected recursion failure, nested conditionals/functions, unsupported
loops/try/async/classes/decorators, hidden unsupported expressions and signature
expressions. Tests verify ASTs remain unchanged, calls have independent results,
and uploaded side-effect/import/default/decorator code is never executed.
The integration test keeps syntax validity distinct from feature support across
three sibling files. PARSING_FEATURES.md details the boundaries.

First run: 59 tests, one failed assertion expecting a nonzero-width range for an
unmatched parenthesis. CPython reports a point range there. Corrected the test,
retained a separate ranged-error test and added point-span coverage. Final run:
60 tests passed. No parser implementation was changed to invent a wider range.

## Planned commands
Current metadata task verification also ran:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -q
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' examples/show_symbols.py
```
Results: 80 tests passed; calculator demo printed three complete scopes, seven
binding occurrences, two unresolved calls and zero diagnostics. It created no CFGs.
The initial metadata test run had one incorrect assertion counting four calls
in obj.run(factory()()); there are three. Corrected the assertion, then reran the
entire suite successfully. No algorithm was changed to satisfy that mistaken count.

New coverage: all parameter kinds/defaults/annotations, lexical shadowing before
assignment, tuple/starred bindings, nonbinding attribute writes, repeated local
assignments, duplicate declarations, files/revisions, Unicode/multiline positions,
definition-time calls, nested-scope isolation, informational imports, global scope
directives, skipped comprehensions/loops, lookup fallback and table ownership.

After phase 1 creates packaging and tests, use Python 3.12+:
```powershell
python -m pip install -e .
python -m unittest discover -s tests -v
```
These are planned commands, not commands successfully run in this setup. Use
standard-library unittest; avoid requiring external test frameworks unnecessarily.

## Required coverage by phase
- Phase 1: valid single/multi-file JSON, missing fields, malformed JSON, wrong
  types, duplicate IDs/keys, invalid revision types, empty file/project and ID preservation.
- Phase 2: syntax errors, mixed good/bad files, unsupported constructs, diagnostic
  spans and safe handling of source with side effects without executing that source.
- Phase 3: zero/multiple/all-kind parameters, function spans, scopes, bindings,
  duplicate definitions, module-level statements, Unicode and multiline locations.
- Phase 4: sequences, if/else, elif, nested conditionals, one/both branches returning,
  early return and unreachable statements. Assert topology, not merely node counts.
- Phase 5: for/while, zero iterations, nested break/continue and return in loops.
- Phase 6: all graph views, mapping/reference/edge integrity, downstream ID agreement,
  JSON roundtrip, determinism, empty graphs, revised/deleted functions and no stale state.
- Phase 7: same-file calls, recursion, builtins, external/unresolved/ambiguous calls,
  local/parameter shadowing and rebound/decorated functions.
- Phase 8: supported imports/aliases, cross-file targets, missing/ambiguous modules,
  unsupported relative/star imports and no name-only target guessing.
- Phase 9: try/except normal paths, handler possibilities, unmatched exceptions,
  handler errors, return-expression failures and explicitly unsupported combinations.
- Phase 10: full JSON integration fixtures; repeated and interleaved project/revision
  requests; source bounds, non-ASCII columns, CRLF; configured resource-limit behavior.

## Invariants and expected results
Every edge endpoint exists in its graph. Every mapping refers to an existing node.
Every graph reference has an existing source node and target graph. Resolved calls
target known functions. Supplied identities/revision are preserved. Return has no
normal fallthrough. Diagnostics identify unsupported accuracy. Public results are
JSON values and identical input produces deterministic output.

## Known limitations
Call-resolution and overview/service coverage is now implemented; see the latest execution section. Runtime tests use Python 3.12.14;
packaging installation, CI, performance and resource limits have not been verified.
Other reserved test files contain no tests and are not evidence of feature coverage.

## Setup verification
Executed a PowerShell inventory, Markdown relative-link check, and Get-FileHash
comparison on 2026-10-29. Result: PASS — all ten required docs exist; 13 Markdown
files total; all six relative links resolve; the preserved master prompt matches
the attachment's SHA-256 hash. This verifies documentation setup only, not software
behavior. No Python tests were run.

## Organization verification
PowerShell checks confirmed eleven package module files, eight reserved test files,
valid calculator JSON, and SHA-256 agreement for all seven extracted reference files
against their ZIP entries. Cached bytecode was excluded. Python commands were not
available on PATH in this shell; package installation and Python tests were not run.

## File organization verification — 2026-11-03
Executed from the repository root:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -q
```
Baseline result: `Ran 113 tests` / `OK`. Post-refactor result: `Ran 117 tests` /
`OK`, zero failures/errors. Existing tests verify JSON intake, ProjectAnalysis
construction and serialization, mappings/references, CFG behavior and revision
isolation. Four added tests verify package imports, canonical model identity,
legacy module aliases and feature-validator exports. FlowchartOutput/MappingOutput
structures cannot be exercised because their implementations do not exist yet.
No reference/uploaded source was executed.

Also executed with the same Python runtime and PYTHONPATH:
`python examples/show_symbols.py` — exit 0; three complete scopes, seven binding
occurrences, two unresolved calls and zero diagnostics.

## Phase 0 audit and Phase 1 verification — 2026-11-03
Baseline full suite: 117 passed. Final full suite: 127 passed, zero failures/errors.
Executed from the repository root:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -q
```
The existing 15 validator tests now use InputValidator.validate and continue to
cover valid input, all required fields, incorrect types, duplicate IDs, malformed
JSON, invalid revisions, exact identities and request isolation. Five new boundary
tests verify class/function/legacy equivalence, revision zero, syntax separation,
no ast.parse call and fresh state. Five added ID tests cover production kinds,
graph-owned node/edge ordinals, tuple boundaries, invalid kinds and the exact
existing fb1_ encoding. Existing CFG/analyzer tests verify shared ID conventions.

Phase 0 AST inventory found no duplicate source classes or explicit relative
module import cycles; unused field/Literal imports remain a documented cleanup
item. Import/identity tests pass, including the added validator module alias.
Audit findings beyond Phase 1 were not fixed or newly claimed as implemented.

Targeted checks also executed using the same runtime and PYTHONPATH:
- `python -m unittest discover -s tests -p 'test_*validator.py' -q`: 34 passed
  (input and feature validation suites).
- `python -m unittest discover -s tests -p 'test_ids.py' -q`: 9 passed.

## Phase 2 model verification — 2026-11-03
After model changes, the existing suite passed 127 tests. Added 12 behavior tests
in test_model_integrity.py. Executed with src on PYTHONPATH:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -p 'test_model*.py' -q
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -q
```
Results: 26 focused model tests passed; 139 full-suite tests passed; no failures.
New coverage: graphType JSON shape, legacy constructor/property compatibility,
conflicting/invalid graph types, optional typed labels, fresh list defaults,
mutated nested records, AST rejection, dangling reference/mapping source/targets,
duplicate mappings, graph-local node identity, cross-graph edge rejection, call
ownership and recursive JSON-only output. Existing CFG tests remain unchanged.

Also executed the DATA_MODELS.md containment example: PASS. Static AST traversal
of concrete model imports found no cycles; package import tests passed in the suite.

## Requested Phases 3/4 verification — 2026-11-03
Executed with src on PYTHONPATH using the bundled Python runtime:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -q
```
Initial run: 139 tests, one failure because an earlier analyzer test expected
ordinary loops to be omitted. Updated that expectation to include j and nested(j),
while retaining lambda/comprehension isolation and incomplete-scope assertions.
Added 12 tests in test_parsing_metadata_phases.py. Final full suite: 151 passed,
zero failures/errors. Existing CFG tests pass unchanged; no CFG construction added.
New cases cover file identity, path metadata, nested if/elif/else and loop context,
conservative try and unsupported classes, mixed-validity multi-file processing,
exact calculator spans/parameters/symbol lookup, loop calls/bindings/shadowing,
zero-iteration lexical bindings, nested-function isolation inside loops, remaining
try/loop-else omissions, duplicate names across scopes/files and mutated parent cycles.
Existing parser tests continue to verify no execution/import/default evaluation,
UTF-8 spans, empty inputs and resource/encoding failures. Existing metadata tests
cover parameter kinds, Unicode, nested scopes and revision isolation.

Additional executed checks (same runtime/PYTHONPATH):
- `python -m unittest discover -s tests -p 'test_parsing_metadata_phases.py' -q`:
  12 passed, including the exact seven-line user calculator example.
- `python examples/show_symbols.py`: exit 0, three complete scopes, seven binding
  occurrences, two unresolved calls, zero diagnostics. This existing demo uses the
  earlier branching calculator fixture; its line numbers differ from the user's
  seven-line example and are not presented as that example's output.

## Phase 5A verification — 2026-11-03
Added tests/test_cfg_branches.py with seven complete edge-multiset assertions.
Endpoints are distinguished by label and source line so repeated text does not
collapse distinct nodes. Tests cover sequential/implicit completion, if/else merges,
missing and pass else, nested repeated labels, elif returns, unreachable diagnostics
and omitted mappings, and bare returns. Prior tests cover AST spans, IDs, ownership,
revision isolation and recursion failures. Existing loop/exception tests unchanged.
Executed from repository root:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -p 'test_cfg*.py' -q
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -q
```
Results: 40 CFG tests passed; 158 full-suite tests passed. Zero failures/errors.

## Phase 5B verification — 2026-11-03
Added tests/test_cfg_loops.py with 12 tests covering exact while-else and for-else
connectivity, break bypass, continue advancement, false/true literal conditions,
infinite-loop unreachable paths, early returns, nested break ownership, inner-else
break/continue targeting outer loops, invalid else controls, loops nested inside
else, exception bypass, mapping integrity, deterministic IDs and revision isolation.
Existing Phase 5A sequence/branch/return tests and other loop/exception tests pass.
Adjusted the previous loop-else rejection test to retain only outside-loop control
rejections; loop-else now has dedicated positive and boundary coverage.

Executed with the bundled Python runtime from the repository root:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -p 'test_cfg*.py' -q
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -q
```
Results: 52 CFG tests passed; 170 full-suite tests passed, zero failures/errors.
Before the 12 new tests, the existing 158-test suite also passed after the change.
No uploaded source executed; existing incomplete loop-else metadata tests still pass.

## Phases 5C/6 verification — 2026-11-03
Command (PowerShell, repository root):
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
& 'C:/Users/bhars/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m unittest discover -s tests -q
```
Result: **183 tests passed**, zero failures/errors (0.730 seconds).
New test_cfg_exceptions.py: 2 tests, exact bare-handler topology and nested-handler
try rejection. Existing exception tests cover normal bypass, ordered handlers,
return-expression failure, terminal returns, loop interactions and unsupported forms.
New test_call_resolver.py: 11 tests covering lexical/forward/recursive calls,
builtins, absolute imports and aliases, dotted modules, shadowing, duplicate
bindings/modules, no global name guessing, external/failed modules, dynamic/relative/
conditional/local imports, incomplete scopes, deterministic output and revision IDs.
All source fixtures are parsed as data, never executed. No runtime equivalence or
full exception/name-resolution semantics is claimed.

## Phases 7/8 test evidence — 2026-11-03
Executed with PYTHONPATH=src using the bundled Python 3.12 runtime:
`python -m unittest discover -s tests -q`: **194 passed**, zero failures/errors
(0.903 seconds). Earlier pre-extension run: 192 passed.
New tests/test_pipeline.py covers calculator JSON, same/multi-file hierarchy,
multiple functions, empty files/projects, failed sibling parsing, unsupported module
and function behavior, graph/mapping integrity, missing/duplicate graph rejection,
reused function graphs, determinism/revision isolation, projection snapshot isolation,
approved Kevin metadata, import bindings and UTF-8/CRLF mapping positions.
Executed `python examples/generate_outputs.py`: calculator success/4 graphs/3 links;
multi-file partial/5 graphs/4 links. All four generated JSON files were read back
and compared to their projections. Uploaded fixture source was parsed, never run.

## Phases 9/10 actual execution results — 2026-11-03
All commands use PYTHONPATH=src and the bundled Python 3.12.14 executable previously
recorded above. Command: `python -m unittest discover -s tests -q`.
- Baseline: 64 entries, 14 import errors due to ProjectGraphs/ProjectGraphResult mismatch.
- First repair: 194 passed (1.015 seconds).
- Concurrent external placeholder replacement: 65 entries, 15 import errors.
- After user paused other editor and builder restoration: 205 passed (1.724 seconds).
- Final run: **207 passed**, zero failures/errors (1.306 seconds).
No assertion failures occurred in these runs. Import failures prevented affected
modules from loading; those baseline entry counts are not full-suite totals.

New tests/test_reanalysis.py contains 13 tests for editing, deletion, condition/line
changes, same/different revisions/projects, refreshed mappings, invalid edits and
recovery, failed cross-file targets, pathological paths, duplicate parameters,
strict failure-envelope identity and realistic multi-file integration.
`python examples/generate_outputs.py` succeeded: calculator 4 graphs/3 links;
multifile 5/4; orders 7/6. Six output JSON files were round-trip verified. No uploaded
fixture code was executed. No line/branch coverage percentage or production load
capacity was measured. See FINAL_REVIEW.md for remaining limitations.

Final verification after documentation reconciliation: the same full-suite command
again passed 207 tests (1.463 seconds), zero failures/errors. Regenerated all six
consumer fixtures successfully; calculator/multifile/orders graph counts unchanged.

## VS Code runner smoke verification — 2026-11-03
Ran examples/run_analysis.py on conditions, loops, syntax_error, class_unsupported,
unsupported_statement and basic_try inputs, plus orders_input.json. All seven CLI
runs completed successfully, wrote three JSON artifacts each and printed diagnostics.
Observed status/graph counts: conditions success/3; loops success/3; syntax_error
partial/2; class_unsupported partial/2; unsupported_statement partial/3; basic_try
partial/3; orders partial/7. See VSCODE_TESTING.md for reproducible commands.

## Code Manager adapter verification
Executed with PYTHONPATH=src using bundled Python 3.12:
`python -m unittest discover -s tests -q`: 215 passed in 1.481 seconds, no failures/errors.
Eight new tests cover exact preservation/duplicate basenames, JSON/canonical forms,
matching/conflicting aliases, revision validation/conflicts, malformed/cyclic input,
duplicate keys/file IDs, required fields, stateless reuse and syntax-stage separation.
`python examples/run_analysis.py examples/code_manager_input.json --revision-id 1`:
success, revision 1, 3 files, 3 functions, 7 graphs; three output JSON files generated.

## Absolute import correction verification
First full run: 219 tests, 2 failures. Both were adapter-test counts hardcoded to
three files while the user had edited the shared manual sample to five files.
Moved that regression data into the test itself; did not replace the user's input.
Final `python -m unittest discover -s tests -q`: 219 passed in 1.834 seconds.
Ran examples/generate_outputs.py: calculator/multifile/orders all success.
Ran examples/run_analysis.py examples/code_manager_input.json --revision-id 2:
success, 5 files, 10 functions, 16 graphs; no diagnostics printed. Four new import
feature tests verify allowed imports/aliases, rejected forms, resolved graph targets
and external calls without executing imported code.
