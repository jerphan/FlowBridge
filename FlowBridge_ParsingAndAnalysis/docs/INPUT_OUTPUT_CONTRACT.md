# Input and output contract

Status: input models/validation and output model serialization are implemented.
The input shape is unchanged. Output models follow the previously documented
shape; automatic analysis and downstream projections are implemented. JSON keys
use camelCase; Python attributes use snake_case. See DATA_MODELS.md for usage.

## Required input
ProjectInput contains projectId (string), projectName (string), revisionId (integer),
and files (array of FileInput). Every FileInput contains fileId, fileName, filePath,
and fileContent (all strings).

```json
{"projectId":"P001","projectName":"Calculator","revisionId":1,"files":[{"fileId":"F001","fileName":"calculator.py","filePath":"calculator.py","fileContent":"def calculate(a, b):\n    return a + b\n"}]}
```

Implemented validation: identifiers and names/paths must be nonblank strings;
revisionId must be a nonnegative integer (reject bool); fileContent may be empty;
files may be empty. Preserve supplied values without coercion. Reject duplicate
file IDs and malformed JSON, including duplicate object keys and nonfinite numbers.
Unknown fields are ignored after checking that their values are valid JSON data.
Duplicate exact paths produce a warning without discarding files. Cycles, nonfinite
numbers (including overflow such as 1e999), non-string object keys and non-JSON
values in decoded objects are rejected. Missing/invalid fields are collected as
diagnostics, with field paths in messages and known file IDs where available.
No identifier format or UUID requirement is imposed. Path safety/module indexing
rules must be settled before cross-file resolution; never read filePath from disk.

## Canonical result models
ProjectAnalysis fields:
- projectId, projectName, revisionId: copied input metadata; nullable only when invalid/missing.
- status: `success`, `partial`, or `failed`.
- files: FileMetadata array containing fileId, fileName, filePath, graphId, status.
- functions: FunctionInfo array defined below.
- graphs: object keyed by graphId, each value a Graph.
- symbols: SymbolInfo array defined below.
- callReferences: CallReference array defined below.
- sourceMappings: SourceMapping array.
- graphReferences: GraphReference array.
- diagnostics: Diagnostic array.

GraphModel: graphId; graphType (`project`, `file`, `function`, `module`); fileId and functionId
(nullable owners); status (`complete`, `unsupported`, `failed`); nodes; edges.
Module graphs require fileId and have null functionId. Their IDs are scoped to
the same project/revision as other graphs. File overviews link to them through
graphReferences. Only function graphs have a functionId.
Unsupported/failed function/module graphs are non-executable, with empty nodes/edges.
Graph IDs remain available for accurate metadata/navigation without fabricating control flow.

The November 6 procedural update adds the `module` graphType value; existing JSON
keys and input fields remain unchanged. Consumers must support this additional
view type. A normal End node may be absent for nonterminating flow. Source mappings
continue to use `(graphId, nodeId)` and unchanged UTF-8 byte-coordinate semantics.

FlowNode: nodeId, nodeType, label, sourceLocation (SourceLocation or null).
Model node types: `file`, `function`, `start`, `end`, `statement`, `condition`,
`loop`, `return`, `break`, `continue`, `exceptionDispatch`, `handler`, `raise`.
FlowEdge: edgeId, sourceId, targetId, edgeType, label (string or null).
Model edge types: `next`, `true`, `false`, `back`, `break`, `continue`, `return`,
`exception`, `unhandled`. Endpoints are within the owning graph. Overview graphs
initially have no edges; containment/navigation uses GraphReference.

SourceLocation: fileId, startLine, startColumn, endLine, endColumn (integer coordinates).
SourceMapping: graphId, nodeId, location (non-null SourceLocation).
GraphReference: sourceGraphId, sourceNodeId, targetGraphId.
FunctionInfo: functionId, functionName, qualifiedName, fileId, parameters,
startLine, endLine, startColumn, endColumn, graphId, scopeId.
ParameterInfo: name, kind (`positionalOnly`, `positionalOrKeyword`,
`varPositional`, `keywordOnly`, `varKeyword`), hasDefault, annotation (source string or null).
SymbolInfo: scopeId, name, kind (`function`, `parameter`, `local`, `import`, `module`),
fileId, location (nullable), functionId (nullable), importTarget (nullable string).
CallReference: callId, fileId, callerFunctionId (nullable for module code), location,
expression, resolution (`resolved`, `unresolved`, `ambiguous`, `builtin`, `external`),
targetFunctionId and targetGraphId (nullable), reason. A resolved call has both targets.
Calls are separate records, never runtime navigation edges. One node can contain multiple calls.
Diagnostic: severity (`info`, `warning`, `error`), code, message, fileId (nullable),
sourceLocation (nullable), graphId (nullable to identify an affected graph).

## Downstream projections
Metadata extraction adds an internal API:
`ASTAnalyzer.analyze(ast.Module, FileInput, RevisionIds) -> ASTAnalysis`.
It contains file_id, module_scope_id, functions, symbol_table, call_sites and
diagnostics. Its to_dict() is a development snapshot, not a new downstream contract.
FunctionInfo and SymbolInfo retain their existing JSON fields. Function graph IDs
are reserved and must not be exposed as navigable graphs before graph construction.

CallSite records use callId, fileId, scopeId, callerFunctionId, location, expression,
calleeExpression and nullable directName. They are syntactic occurrences, not
resolved CallReference records. ScopeInfo describes scopeId, name, kind, fileId,
parentScopeId, functionId and isComplete. isComplete refers to binding extraction,
not feature support or runtime correctness. SymbolTable.lookup returns internal
BindingLookup(scope_id, bindings, is_complete), never a guessed function target.
Additional INCOMPLETE_SCOPE warnings explain omitted constructs. See AST_ANALYSIS.md.

Parsing and feature inspection currently expose Python-only result objects:
`PythonParser.parse(FileInput) -> ParseResult(tree, syntax_valid, diagnostics)` and
`FeatureValidator.validate(ast.Module, file_id) -> FeatureValidationResult` with
diagnostics and is_supported. ParseResult is intentionally not a JsonModel: its
AST must stay internal. syntax_valid is True/False for parser acceptance/rejection,
or None for an encoding/recursion failure. Feature inspection is only called when
tree exists. Existing Diagnostic serialization and downstream JSON keys are unchanged.
Codes: SYNTAX_ERROR, INVALID_SOURCE_ENCODING, PARSER_LIMIT, UNSUPPORTED_FEATURE.
Diagnostics carry fileId, optional sourceLocation and null graphId (no graphs yet).
Unsupported diagnostics name the enclosing function/module in their messages.

FlowchartOutput: projectId, projectName, revisionId, status, graphs,
graphReferences, diagnostics. Graph/node objects preserve canonical IDs.
MappingOutput: projectId, revisionId, status, files, functions, sourceMappings,
graphReferences, callReferences, diagnostics. Consumers join by graphId/nodeId.
Projections contain only JSON values; no ASTs, sets, exceptions, or dataclass instances.

Example shared records (illustrative IDs, not an implemented ID format):
```json
{"sourceMappings":[{"graphId":"g-function-1","nodeId":"n-return-1","location":{"fileId":"F001","startLine":2,"startColumn":4,"endLine":2,"endColumn":16}}],"graphReferences":[{"sourceGraphId":"g-file-1","sourceNodeId":"n-function-1","targetGraphId":"g-function-1"}]}
```

## Identity, ordering, and status
Implemented helper: `RevisionIds(project_id, revision_id).make(kind, *structural_key)`
encodes the full tuple as compact JSON and URL-safe base64 prefixed with `fb1_`.
Distinct tuples have distinct IDs; repeated tuples deliberately return the same
ID. Callers choose owner/position keys. There is no global mutable generator.

Implemented serialization: all model records have `to_dict()` and `to_json()`;
output is camelCase with null optionals. JSON object keys are sorted, lists retain
order. Output deserialization and downstream adapters are not implemented yet.
Use `validate_project(payload)` for input text or decoded dictionaries; its
ValidationResult has project (null on errors), diagnostics, and is_valid.

Generated IDs must use collision-safe encoding of project/revision/owner/structural
identity, not ambiguous concatenation of user IDs. Graph IDs are unique within a
result; node IDs and edge IDs are unique within a graph. `(graphId, nodeId)` is the
node key. Sort where needed and retain source order for deterministic serialization.
IDs need only be consistent within a revision; no stability promise across edits.

Proposed aggregation: invalid input means failed and no analysis graphs; a valid
snapshot with any failed/unsupported analyzed scope is partial; all scopes analyzed
means success. An empty valid project succeeds. Unresolved calls alone do not make
a structurally correct CFG partial. Diagnostics explain every failed/unsupported scope.
Source columns and range semantics are specified in SOURCE_MAPPING.md.

## Phase 1 API clarification — 2026-11-03
`InputValidator.validate(payload) -> ValidationResult` is the class entry point in
InputValidator.py. `validate_project(payload)` and the legacy validator import
remain compatible. Both accept JSON text or decoded JSON objects and enforce the
same existing fields and rules. Invalid Python text can be structurally valid input;
only PythonParser emits SYNTAX_ERROR. No JSON fields or diagnostic codes changed.

RevisionIds scopes every generated ID by projectId, revisionId and kind, followed
by explicit owner/structural key parts. Current function keys use fileId, line,
UTF-8 column and name; function graphs add the function view tag. Node/edge keys
use graphId and a local ordinal; call keys use fileId and the complete AST span.
Same full tuple means the same ID; different supported tuples encode differently.
This does not detect a caller accidentally assigning the same key to two objects.
Supplied projectId/fileId values are never replaced, IDs are not secrets, and
cross-edit identity stability is not promised. See DATA_MODELS.md for an example.

## Phase 2 model change — 2026-11-03 (explicit user request)
Serialized graphs now use graphType instead of viewType, with the same project,
file and function values. FlowEdge adds nullable label. These are intentional
output-contract changes requested in Phase 2; input fields, identifier encoding,
source positions and graph algorithms are unchanged. Consumers of prior graph
JSON must read graphType. No duplicate viewType key is emitted.

GraphModel accepts canonical graph_type or the legacy view_type Python keyword;
conflicting values are rejected. view_type is a compatibility property over the
same field. All remaining owner/status fields are retained. New callers should
use graph_type. Edge labels default to null and do not affect edge_type semantics.

Model validation rechecks nested mutable records at construction/serialization.
Every edge must have graph-local endpoints; every navigation source node and
target graph must exist; every mapping must identify an existing graph/node and
match that node's location. Duplicate mapping keys are rejected. Node/edge IDs are
local to graphs; graph IDs, function IDs, file IDs and call IDs are unique within
their respective revision-level collections. A node is identified by the tuple
(graphId, nodeId), never by concatenating strings with an ambiguous delimiter.
Call source files/locations and non-null caller function ownership are checked.

Models reject ASTs in contract fields and serialize only JSON-compatible values.
ProjectAnalysis holds all currently documented result categories; it does not run
the analysis. Full source-bound checks, scope consistency and one mapping for every
source-backed node remain producer/integration responsibilities. Diagnostics may
refer to invalid input files absent from successful metadata; failure envelopes
are still allowed. No new ImportRelationship contract was invented.

## Phases 3/4 internal API refinement — 2026-11-03
PythonParser now supplies ParseResult.file_id on every result, including successful
and empty parses. It is a Python-only field; ParseResult is not serialized into
public JSON. Existing positional arguments remain compatible via a trailing default.
ASTAnalysis/SymbolInfo/CallSite JSON fields are unchanged. Ordinary for/while
bindings and calls are now extracted into the enclosing lexical scope. Their
isComplete flag can be true if no unsupported binding construct is encountered.
Try and loop-else remain incomplete, with diagnostics. No input contract changed.

## Phase 6 internal relationships
ASTAnalysis additionally retains internal imports: ImportRelationship records.
CallResolver returns CallResolution(call_references, import_relationships).
CallRelationship is an alias of CallReference. No public ProjectAnalysis or output
projection fields changed; no raw AST is present in CallReference serialization.
See CALL_RESOLUTION.md for API boundaries and reserved graph target requirements.

## Phases 7/8 integrated API and approved output extension — 2026-11-03
`ParsingAnalysisService.analyze_project(json_text_or_dict) -> ProjectAnalysis`
validates a complete snapshot, parses each file, extracts metadata/features,
resolves calls, builds CFGs and structural overviews, and validates integrity.
`FlowchartOutput(analysis)` and `MappingOutput(analysis)` expose `to_dict()` and
`to_json()`. They capture independent JSON values and never generate IDs.

Approved additive FlowchartOutput fields: **files, functions, callReferences,
symbols**. Import information is represented by existing import-kind SymbolInfo
records and importTarget. Existing projectId/projectName/revisionId/status/graphs/
graphReferences/diagnostics remain. MappingOutput is unchanged: projectId,
revisionId, status, files, functions, sourceMappings, graphReferences,
callReferences, diagnostics. No new callRelationships/importRelationships wire
keys are introduced. This preserves Grace's navigation/call requirements while
letting Kevin inspect ownership and supported calls/imports. User approval recorded
in D023; this supersedes the earlier shorter FlowchartOutput field list.

Malformed or structurally invalid input returns failed with no graphs. Valid
identity fields in invalid decoded dictionaries or strictly decoded JSON text are
retained; malformed or duplicate-key JSON text returns null identity fields. Valid snapshots are partial if any file fails or
has unsupported/incomplete analysis, including unsupported module execution.
Otherwise they succeed, including an empty snapshot. Warning-only conservative
exception CFGs do not alone cause partial status, but incomplete lexical extraction
does. Unresolved calls alone do not cause partial status. Failed/unsupported function
views remain empty and referenced; graph status must be checked before rendering.

FileMetadata.status describes analysis coverage; a complete file overview describes
structural containment only. A file may therefore be unsupported while its file
graph is complete and holds useful function nodes. Syntax failures have failed,
empty file graphs. No module execution CFG is claimed. Imports are resolved as
metadata while module feature diagnostics remain visible.

Representative generated outputs: examples/calculator_kevin_output.json,
calculator_grace_output.json, multifile_kevin_output.json and
multifile_grace_output.json. Reproduce with examples/generate_outputs.py and PYTHONPATH=src.


## Final review lifecycle clarification
Structurally invalid but strictly decodable JSON text retains individually valid
projectId/projectName/revisionId exactly as decoded dictionary input does. Malformed
or duplicate-key JSON has no trustworthy envelope and uses null identities.
Invalid edited Python in a valid snapshot retains its supplied revision and produces
an empty failed file view plus diagnostics. No older graphs are returned as current.
See INTEGRATION_GUIDE.md for response matching and consumer status handling.

## Code Manager adapter (approved boundary addition)
CodeManagerInputAdapter lives in src/flowbridge_analysis/CodeManagerInputAdapter.py.
It accepts Code Manager projectID/fileID names and normalizes them to the existing
projectId/fileId contract. It preserves IDs, paths, source text and line endings.
Matching alternate spellings are accepted; conflicting spellings are rejected.
normalize(payload, *, revision_id) returns a fresh validated dictionary or raises
ValueError for invalid input. The supplied revision must be a nonnegative integer;
an existing payload revision must match. Strict JSON decoding rejects duplicate keys.
The adapter reuses InputValidator and does not parse or execute Python source.
ParsingAnalysisService and both consumer schemas remain unchanged.

The adapter inserts the supplied revision into each snapshot; it does not retain
or increment a counter. The coordinating backend owns revision allocation; the
local runner receives it through --revision-id. No automatic default is supplied.


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
