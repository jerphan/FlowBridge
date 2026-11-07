# Team integration guide

## Justin: complete source snapshots
Use Python 3.12+ with the installed package or src on PYTHONPATH. Justin supplies projectID, projectName and stable fileID values. The coordinating backend supplies revisionId; the adapter normalizes names. Send every current
Python file on every request, including unchanged files. Omit deleted files;
use an empty fileContent to represent an empty file. Required file fields are
fileId, fileName, filePath and fileContent. Input may be JSON text or a decoded
JSON dictionary. Do not pass a ProjectInput instance to this entry point.

```python
from flowbridge_analysis import ParsingAnalysisService, FlowchartOutput, MappingOutput

payload = {
    'projectId': 'P001', 'projectName': 'Calculator', 'revisionId': 7,
    'files': [{'fileId': 'F001', 'fileName': 'calculator.py',
               'filePath': 'calculator.py',
               'fileContent': 'def add(a, b):\n    return a + b\n'}],
}
analysis = ParsingAnalysisService().analyze_project(payload)
kevin_json = FlowchartOutput(analysis).to_json()
grace_json = MappingOutput(analysis).to_json()
```

This invokes static analysis only. File paths are metadata, not paths to read or
import. Use unique root-relative Python paths for cross-file absolute imports.
The service does not provide HTTP transport, upload handling, authentication,
request scheduling, database storage, UI editing or debounce logic.

## Kevin: graphs and navigation
FlowchartOutput contains projectId, projectName, revisionId, status, graphs,
graphReferences, diagnostics, files, functions, callReferences and symbols.
The last four fields were approved as additive fields in D023. Imports appear
as kind=import symbols with importTarget; there is no importRelationships wire key.
Find the project graph by graphType=project. Graphs is a dictionary keyed by the
opaque graphId; never decode IDs or derive labels from them. Node IDs are local to
a graph. Edges connect nodes only inside that graph and describe control flow.
Kevin owns layout, coordinates, styling and rendering.

November 6 update: handle `graphType=module` alongside project/file/function.
Files with top-level execution gain a file-view navigation node pointing to their
module CFG. Module function-definition nodes can navigate to function CFGs using
the same graphReferences contract. Render their real nodes/edges and retain their
IDs for Grace's source lookup. Do not assume every CFG has a normal End node.
Module-level callReferences use lexical targets; they do not prove runtime
definition order or model import side effects.

Selecting a project file node: find the graphReference matching sourceGraphId
and sourceNodeId, then open graphs[targetGraphId]. Selecting a file function node
uses the same procedure to open its function CFG. References are navigation,
not execution edges. File/project overviews have no control-flow edges.
Check graph.status: failed/unsupported graphs are intentionally empty. A complete
file overview does not assert complete module execution analysis; inspect the
corresponding FileMetadata.status and diagnostics. Calls are separate records;
only resolution=resolved has targetFunctionId and targetGraphId. A resolved target
can itself be unsupported, so check its graph status before displaying paths.

## Grace: highlights, source navigation and calls
MappingOutput contains projectId, revisionId, status, files, functions,
sourceMappings, graphReferences, callReferences and diagnostics. It does not carry
a second graph dictionary. Join to Kevin's graph dictionary from the same revision.
CallRelationship is a Python alias; the JSON key stays callReferences.

Look up sourceMappings by (graphId, nodeId). Locations contain fileId, startLine,
startColumn, endLine, endColumn. Lines are one-based, columns are zero-based UTF-8
byte offsets, and end positions are exclusive. Use Justin's exact revision source
and convert byte offsets to the editor's Unicode/UTF-16 coordinate system.
Do not slice JavaScript strings using byte offsets. Synthetic Start/End and project
file nodes have no mappings. File function nodes map to whole function spans;
CFG nodes map to statements/expressions. Overlaps are expected; reverse lookup may
return several nodes. Diagnostic locations can be null or zero-width points.

## Revision handling and edited-source failures
Each call rebuilds the entire snapshot with fresh parser/CFG/table/collection
state. There is no previous-result fallback or server-side latest-revision cache.
RevisionIds includes projectId and revisionId in every generated identity. Input
file IDs are preserved. IDs are deterministic for identical inputs but are not
stable across revisions or a reliable indication of content equality.

The coordinating backend should assign a new revisionId to every changed snapshot, never reuse one
for different text. The future UI tracks the current projectId and requested
revisionId. Accept a response only when BOTH match that current request, even if
an older response finishes later. Pair Kevin and Grace outputs only for the same
project/revision. Clear/replace prior maps and graphs atomically; do not merge old
and new arrays. Reusing a revision for different text still triggers fresh analysis,
but the UI cannot distinguish those responses from revisionId alone. The stateless
service accepts older revisions; ordering is the caller's responsibility.

When a file becomes syntactically invalid, its latest file view is failed and
empty, with a syntax diagnostic. Its former functions, CFGs, symbols, mappings and
call sites are absent. Other files are freshly analyzed, and calls to the failed
module become unresolved. Project/file navigation still identifies that failed
file. Valid snapshots with any failed/unsupported/incomplete file return partial;
a fully supported snapshot (including empty project) returns success. Structurally
invalid input returns failed with no graphs. Do not display an old valid CFG as the
result of a newer invalid edit. A separately labeled previous-version view would
be a UI decision, never current analysis data.

## Supported subset and integration gates
Supports direct functions, parameters/local bindings, sequences, conditions,
returns, loops/break/continue/loop-else CFGs, bounded non-nested try/except CFGs,
and conservative direct/absolute-import call resolution. See CFG_DESIGN.md,
PARSING_FEATURES.md and CALL_RESOLUTION.md for exact boundaries.

Imports can resolve as metadata while module execution remains unsupported and
the project is partial. Try/loop-else lexical extraction remains incomplete.
Classes, closures, async, comprehensions, finally/nested try, dynamic calls,
relative imports and full runtime semantics are unsupported. Expressions are
atomic CFG operations. No AST or uploaded source execution occurs.

Resource quotas/process isolation, full compiler-context validation, editor
coordinate conversion and live consumer testing remain integration work. Use
controlled fixtures for team integration; do not claim arbitrary untrusted-upload
production readiness. Exact UML images were unavailable; documented contracts and
explicit approved extensions control the implementation.

## Fixtures and verification
Run `python -m unittest discover -s tests -q` with PYTHONPATH=src.
Run `python examples/generate_outputs.py` to regenerate calculator and multi-file
consumer JSON. The JSON includes long opaque IDs intentionally; consume them
unchanged. FINAL_REVIEW.md and TESTING.md record the actual latest results.

The realistic fixture is examples/orders_input.json: pricing.py defines a quantity
discount, orders.py totals valid line items using an imported alias and a loop,
and report.py calls the order module through an alias and prints the total.
Generated orders_kevin_output.json and orders_grace_output.json share all identities.
Its partial status is expected because module imports are metadata-only analysis.

## Using actual Code Manager JSON
The actual external keys are projectID and fileID, and revisionId may be absent.
Use the adapter before the existing service:
```python
from flowbridge_analysis import CodeManagerInputAdapter, ParsingAnalysisService
normalized = CodeManagerInputAdapter().normalize(code_manager_payload, revision_id=1)
analysis = ParsingAnalysisService().analyze_project(normalized)
```
For a backend, replace 1 with the revision assigned to this request by its coordinator.
normalize raises ValueError on malformed/conflicting input; handle that as an input
error in the transport layer. The CLI prints it as an argument error before writing
outputs. Syntax errors in fileContent are handled later as analysis diagnostics.
The adapter keeps no revision counter. For local use, run:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python examples/run_analysis.py examples/code_manager_input.json --revision-id 1
```
Observed result: success, revision 1, 3 files, 3 functions, 7 graphs. Outputs are
examples/results/code_manager_input/analysis.json, flowchart.json and mapping.json.

## Placement inside the main FlowBridge repository
Keep this package together under FlowBridge/FlowBridge_ParsingAndAnalysis/:
- src/flowbridge_analysis/: production adapter, service, components, models, outputs.
- pyproject.toml: installable package metadata.
- tests/: regression tests.
- docs/: contracts, limitations and integration instructions.
- examples/: reusable input fixtures and demonstration scripts.
- .gitignore: ignores generated local examples/results/ output and Python caches.

Do not put incoming user JSON inside src/. Production integration passes JSON
in memory to the adapter/service and returns JSON values to consumers. There is no
required input/output directory for production. examples/ is only for demonstrations
and tests. Some regression tests read example inputs, so deleting examples/ breaks
those tests unless their fixtures are relocated and the tests updated.
Keep small curated example input/output fixtures; ignore generated examples/results/.
Do not commit uploaded user projects, .venv, caches or credentials. Ignoring a path
does not untrack it if it was already committed; inspect the Git changes before push.

From FlowBridge/FlowBridge_ParsingAndAnalysis in a PowerShell terminal:
```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python examples/run_analysis.py examples/code_manager_input.json --revision-id 2
```
Production Python backend setup can install this local package into its environment
from the FlowBridge repository root:
```powershell
python -m pip install -e ./FlowBridge_ParsingAndAnalysis
```
Then import flowbridge_analysis normally; the outer folder name is not the Python
import name. Deployment must include/install the package too. Python 3.12+ is required.

## AI Studio integration handoff (implementation instructions)
The backend framework is not identified in this module. Integrate in the actual
application backend; do not execute this Python package directly in a browser.
If the backend is JavaScript/TypeScript, add a Python API/service boundary. The
HTTP route and response envelope below are proposed transport choices, not existing
endpoints or changes to the two approved consumer contracts.

1. Receive Code Manager's complete projectID/projectName/files snapshot with fileID.
2. Assign a revision for that project/snapshot before dispatch; communicate the same
   value to the UI. Do not rely on a counter inside the adapter or a constant 1.
3. Normalize with CodeManagerInputAdapter.normalize(payload, revision_id=revision).
4. Analyze once with ParsingAnalysisService.analyze_project(normalized).
5. Produce FlowchartOutput(analysis).to_dict() and MappingOutput(analysis).to_dict().
6. Deliver the first object to Kevin and the second to Grace. A suggested combined
   HTTP response is {"flowchart": <first object>, "mapping": <second object>}.
7. Handle adapter ValueError as invalid input. Retain partial analysis diagnostics;
   partial is a usable result, not automatically a transport failure.
8. The UI only applies responses for its current projectId/revisionId. Replace both
   views together; never mix older source mappings with current graphs.
9. Keep analysis in memory. Do not use examples/results/ as a backend communication
   channel, execute uploaded source, or let consumers regenerate analysis IDs.

Example Python integration body (payload and revision supplied by the backend):
```python
from flowbridge_analysis import (
    CodeManagerInputAdapter, ParsingAnalysisService, FlowchartOutput, MappingOutput,
)
normalized = CodeManagerInputAdapter().normalize(payload, revision_id=revision)
analysis = ParsingAnalysisService().analyze_project(normalized)
response_body = {
    'flowchart': FlowchartOutput(analysis).to_dict(),
    'mapping': MappingOutput(analysis).to_dict(),
}
```
An HTTP framework should serialize response_body once. to_json() is available for
writing files/raw JSON strings; do not double-encode those strings in a JSON response.



## Supported absolute imports — current behavior
Direct module-level `import module [as alias]` and
`from module import name [as alias]` (including multiple names) are accepted as
static metadata. They no longer produce UNSUPPORTED_FEATURE merely for being
imports. ASTAnalyzer records bindings/import relationships; CallResolver uses the
SymbolTable and project module index to resolve supported targets. No import is
executed and no module-execution CFG is claimed. Relative/star imports, future
directives, conditional imports and function-local imports remain unsupported.
Missing external modules have external call status rather than invented targets.
The calculator, imported calculator and order-reporting fixtures now return success.
Earlier partial-status observations for ordinary absolute imports are historical
and superseded by this correction. No input/output field names changed.
