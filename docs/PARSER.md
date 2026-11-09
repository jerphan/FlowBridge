# Parser architecture and contract

## Responsibilities

Python 3.12 is the baseline. Analyze complete snapshots without executing uploaded
source, importing its modules or installing dependencies. Preserve IDs/revisions.
Acquisition, UI, layout and account features are outside the analysis module.

| Component | Responsibility |
| --- | --- |
| InputValidator | Validate snapshot/JSON input |
| PythonParser | Parse with ast and report syntax/resource errors |
| FeatureValidator | Inspect supported constructs/compiler context |
| ASTAnalyzer, SymbolTable | Definitions, scopes, bindings and call sites |
| CallResolver | Bounded lexical/project import resolution |
| CFGBuilder | Source-backed control-flow graphs |
| ProjectGraphBuilder | Project containment and import relationships |
| ParsingAnalysisService | Stage file results and assemble validated analysis |
| FlowchartOutput, MappingOutput | Consumer projections of the same result |
| RevisionIds | Deterministic project/revision/owner IDs |

Components use established PascalCase filenames under
`FlowBridge_ParsingAndAnalysis/src/flowbridge_analysis/`. Serializable contracts
live in `models/`; published aliases remain available.

## Input/output

`ProjectInput`: projectId, projectName, revisionId, files. Each file has fileId,
fileName, filePath, fileContent. IDs/names are nonblank, content may be empty,
revision is a nonnegative integer rather than bool. Preserve values without coercion.
Reject malformed/non-JSON data and duplicate IDs. Paths are metadata, not disk access.
CodeManagerInputAdapter translates ID casing without changing source or ownership.

`ProjectAnalysis`: project/revision identity, status, files, functions, graphs,
symbols, callReferences, sourceMappings, graphReferences and diagnostics.

- Result status: success, partial, failed.
- Graph: graphId, graphType, owner IDs, status, nodes, edges.
  Types: project/file/function/module. Status: complete/unsupported/failed.
- Node: nodeId, nodeType, label, nullable sourceLocation. Types include file,
  function, start/end, statement, condition, loop, return, break/continue,
  exceptionDispatch, handler and raise.
- Edge: edgeId, sourceId, targetId, edgeType, nullable label.
  Types: next, true/false, back, break/continue, return, exception, unhandled.
- GraphReference: source graph/node and target graph. Navigation, execution
  edges and CallReferences are separate relationships.
- Call resolution: resolved, unresolved, ambiguous, builtin or external.
  Only resolved calls have target function/graph IDs.
- SourceMapping: graphId, nodeId, location. Location has fileId, start/end
  lines/columns: one-based lines, zero-based UTF-8 byte columns, exclusive end.
  A node is identified by its owning graph and node ID.
- Diagnostic: severity, code, message, nullable file/graph IDs and source range.

Canonical dataclasses validate these fields and reference integrity. Projections
preserve identities/ranges. Never serialize raw ASTs, sets or exceptions.

## Supported analysis

Assignments, calls, branches, loops/loop-else, return, break/continue and bounded
try/except/else/finally/raise are supported. Direct absolute/relative package
imports feed static resolution. Parameters, rebinding and ambiguous symbols
prevent name-only guesses. Most expressions remain atomic.

File views contain execution with bounded same-file call expansion; function
views contain clickable resolved calls. Cross-file calls navigate to existing
graphs. Recursion is bounded. Returning an expanded call does not fall through.

CFG blocks carry pending normal predecessors. Terminal paths stop normal flow.
Finally gets separate cleanup copies for distinct continuations; cleanup can
override the pending return/exception/break/continue. Nested unmatched exceptions
reach enclosing handlers. Exception edges are conservative possibilities,
not inferred runtime exception types.

File CFGs publish together. Failure discards partial state and recomputes
surviving call targets while keeping valid siblings. Later file-view failure
retains valid function graphs and an empty failed file view. Noncomplete executable
graphs are empty rather than misleading.

Each view is capped at 2,500 nodes. Larger expansion reports CFG_LIMIT and partial
status instead of overwhelming layout. Parser/recursion limits also report
diagnostics; this is not complete process isolation.

Classes, async, closures, comprehensions/generators, try-star, dynamic execution,
and complete Python runtime name/type/exception semantics remain unsupported.
They produce explicit diagnostics rather than executing code.

## Decisions

D019 keeps graphType/nullable labels and legacy aliases. D025 adapts Code Manager
casing while preserving source, IDs and caller revisions. D029 preserves resolved
calls, relative imports, staged publication and correct finally continuations.

The November 9 demo pass adds bounded graph expansion, automatic expiry of inactive
source snapshots and display-only comment ranges. Canonical IDs, source coordinates
and schemas are preserved. Historical phase/audit notes remain in Git history.
See [VALIDATION.md](VALIDATION.md) for executed results.
