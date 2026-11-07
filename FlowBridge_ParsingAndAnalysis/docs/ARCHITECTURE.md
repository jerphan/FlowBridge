# Architecture

Status: typed models, JSON input validation and deterministic IDs are implemented.
PythonParser, FeatureValidator, ASTAnalyzer, SymbolTable and CFGBuilder are implemented;
CallResolver supports bounded lexical/import resolution; overview, service and consumer projections are implemented. See PARSING_FEATURES.md for precise APIs. Starter code
remains separate in reference/. See DATA_MODELS.md for the implemented foundation.

## Pipeline and component interfaces
1. InputValidator.validate in `InputValidator.py` converts a JSON string or mapping into
   typed ProjectInput/FileInput models, or structured contract diagnostics.
2. `PythonParser.parse(file_input)` calls `ast.parse(fileContent, filename=filePath)`
   and returns a request-local parse result with an AST or syntax diagnostic.
3. `FeatureValidator.validate(tree, file_id)` identifies unsupported constructs
   and affected scopes. It must not downgrade unsupported control flow to statements.
4. `ASTAnalyzer.analyze(tree, file_input, ids)` extracts function metadata, scopes,
   bindings, and call sites. Module statements remain explicitly module-owned.
5. `SymbolTable` indexes declarations/bindings by lexical scope. `CallResolver`
   combines these indexes with a project module index to resolve only supported calls.
6. `CFGBuilder.build(function, file_input, ids)` creates nodes and edges with source
   locations immediately attached. `build_module(tree, file_input, ids)` builds
   a separate module CFG for top-level execution. Both return graphs and diagnostics.
7. `ProjectGraphBuilder.build(files, functions, graphs)` constructs overview graphs
   and navigation references to existing graphs only.
8. `ParsingAnalysisService.analyze_project(project_input)` assembles ProjectAnalysis
   and validates integrity; pure output adapters derive FlowchartOutput/MappingOutput.

`models/` owns serializable dataclasses and serialization conventions;
`outputs/` reserves the future projections, not independent analysis or ID generation.
`ParsingAnalysisService.py` coordinates components rather than implementing their algorithms.

Implemented entry point: `validate_project(payload) -> ValidationResult` in
`InputValidator.py` (also exposed as `InputValidator.validate`). `RevisionIds.py` provides stateless `RevisionIds(project_id, revision_id)`
with `make(kind, *key)` to encode owner and structural identity. There are no
global counters or caches. ProjectAnalysis can be constructed and serialized;
this does not imply the orchestration pipeline or downstream projections exist.

## API decisions still provisional
The implemented metadata stage creates a fresh SymbolTable for each file and uses
an explicit RevisionIds context. Scope parents stay within that file. ASTAnalysis
is an intermediate record, not ProjectAnalysis; reserved function graph IDs do not
create graphs. SymbolTable exposes nearest lexical binding groups and incomplete
scope indicators; bounded call resolution is implemented separately; see CALL_RESOLUTION.md.
See AST_ANALYSIS.md for the beginner-friendly algorithm and calculator demonstration.

The implemented project entry point returns ProjectAnalysis, including structured failure results.
Invalid identity fields remain null in a failure envelope rather than invented IDs.
`analyze_file(file_input)` is proposed to return FileAnalysis with only file-local
metadata, diagnostics, and graphs; it cannot resolve project-wide imports.
Prefer diagnostics on each result over a mutable service-level last-result cache.
The suggested no-argument `collect_diagnostics()` conflicts with a fully stateless
service: defer that convenience API; recommend `result.diagnostics` instead.

## Lifecycle and failure isolation
Each call creates fresh state. ASTs never escape into public JSON. Valid sibling
files may still be analyzed when another file fails. Unsupported functions have
an explicit unsupported graph status and no misleading executable CFG. Module-level
control flow is recognized and diagnosed where unsupported; initial file views
are structural overviews, not module execution CFGs.

November 6 update: supported top-level statements now get a separate module CFG;
file overviews retain their structural role and link to that graph. Function
definition nodes link to function views. This supersedes earlier module-execution
deferrals below. The service publishes a file's functions, symbols, graphs,
mappings, and references together after construction succeeds; a failed file
retains a failed file overview and diagnostic without corrupting valid siblings.

No uploaded imports are executed. Paths are metadata used for module indexing,
not instructions to read arbitrary local files. No database or caching layer is planned.

## Teaching guide for future implementations
For each component, explain its input and output using a small example, walk through
its algorithm, identify its consumers, and demonstrate relevant tests and limits.
For example, an AST describes `if` syntax; a CFG describes the alternative execution
paths; a GraphReference opens another view without asserting execution takes that path.

## File organization (2026-11-03)
Implemented components use PascalCase filenames matching their classes. Models
are split into class-named files under `models/`; its initializer preserves public
exports. Shared serialization and type aliases live in `models/JsonModel.py`.
FeatureValidator and its result are in `FeatureValidator.py`; JSON validation
now lives in `InputValidator.py`, with a stateless InputValidator class and the
compatible validate_project function. The legacy validator module path aliases
this module, retaining its former feature API re-exports. Legacy
component imports alias canonical modules. Former component scaffolds now contain
implemented algorithms; outputs/ holds both implemented projection classes.
See FILE_ORGANIZATION.md for the complete before/after inventory and mapping.

## Phase 2 model completion — 2026-11-03
The nine requested core models already existed as typed dataclasses. GraphModel
now exposes graph_type/graphType (legacy Python view_type remains an alias), and
FlowEdge has optional label. JsonModel explicitly traverses model fields and nested
containers, validates mutated child records, and rejects non-contract values.
ProjectAnalysis indexes nodes by (graphId, nodeId) for navigation/mapping checks;
its result fields still group all documented categories for one revision.
Model dependencies remain directed concrete imports; no parser or CFG dependency
was introduced. The existing Diagnostic, FileInput and CallReference provide
supporting records. AnalysisDiagnostic, SourceFile, CallRelationship and
ImportRelationship classes are absent; imports remain SymbolInfo metadata.
No duplicate alias classes were created. See DATA_MODELS.md for a small example.

## Requested Phases 3/4 completion — 2026-11-03
PythonParser preserves file identity in its internal ParseResult; FeatureValidator
uses named traversal context with unchanged supported-language semantics.
ASTAnalyzer now extracts ordinary loop bindings/calls in the enclosing scope and
feeds them to SymbolTable. Table lookup stays lexical and detects mutated parent
cycles. Try/loop-else extraction, closures and complete runtime name resolution
remain unsupported/incomplete. No service, resolver, CFG or output algorithms were
added. PARSING_FEATURES.md and AST_ANALYSIS.md explain the stage boundaries.

## Phase 5B loop-else integration
CFGBuilder separates exhaustion/false paths from break exits and builds else after
removing the finished loop's body context. FeatureValidator uses matching depth
rules. ASTAnalyzer still conservatively omits loop-else binding subtrees and marks
them incomplete; consumers must retain this diagnostic despite supported CFGs.
No public model/schema changes or new service responsibilities were introduced.

## Phase 6 call-resolution integration
CallResolver.resolve(files, analyses) returns CallResolution with canonical
CallReference objects and internal ImportRelationship objects. ASTAnalyzer collects
precise import binding metadata; SymbolTable retains lexical lookup responsibility.
CallRelationship aliases CallReference; public JSON keys are unchanged. Module paths
are snapshot metadata, never filesystem accesses. See CALL_RESOLUTION.md for the
supported imports, calculator example, statuses and runtime limitations.


## Phases 7/8 implementation — 2026-11-03
ProjectGraphBuilder.build(files, functions, function_graphs, ids) returns
ProjectGraphs(graphs, graph_references, source_mappings). It reuses existing
function CFG objects, rejects duplicate/missing graphs and incorrect ownership,
and creates one project view plus one file view per supplied file. Project IDs use
ids.make('graph', 'project'); file IDs use ids.make('graph', 'file', fileId).
Overview node keys include the owning graph plus fileId/functionId. Existing
function CFG IDs remain unchanged. Structural overview graphs have no edges.

ParsingAnalysisService now orchestrates validation, parsing, ASTAnalyzer (which
collects FeatureValidator diagnostics), call resolution, CFG construction,
hierarchy construction and canonical assembly. All intermediate state is local.
Parser failures preserve sibling results. ProjectAnalysis validates references,
edge endpoints, mappings and resolved call ownership; the service additionally
checks complete coverage of all source-backed nodes. Projections validate the
canonical object again and capture independent JSON values. No source is run,
no database exists, and no frontend was implemented.

FlowchartOutput and MappingOutput live under outputs/ and are exported from the
package. Kevin's additive metadata fields were explicitly approved; Grace's existing
contract is sufficient. See INPUT_OUTPUT_CONTRACT and D023. Both projections share
the canonical IDs and diagnostics; neither reconstructs graphs or mappings.

Frontend navigation example: select a file node in the project graph, find the
GraphReference with that sourceGraphId/sourceNodeId, and open its targetGraphId.
Select a function node there and follow its reference to the existing function
CFG. Inspect target graph status before displaying executable paths. Grace can
join sourceMappings by (graphId, nodeId); calls use separate callReferences.


## Requested Phase 9: editing lifecycle
ParsingAnalysisService is deliberately stateless: complete snapshots are rebuilt
on every invocation, including repeated or older revisions. No source editor,
debouncing, persistence or latest-result cache is implemented. Revised source does
not mutate earlier result objects. Identical input is deterministic; a different
revision changes generated IDs without changing Justin's project/file IDs.
Syntax errors yield fresh empty failed file views and diagnostics, preserve valid
siblings, and remove obsolete call targets. UI response ordering is explicitly the
consumer's responsibility; see INTEGRATION_GUIDE.md.

## Review corrections and lifecycle (2026-11-03)
The builder accepts existing function graphs as either a list or dictionary;
ProjectGraphs aliases ProjectGraphResult. The result exposes combined graphs plus
project_graph/file_graphs/files and a collision-checking combine_graphs helper.
A complete structural file overview may coexist with unsupported file analysis;
syntax-failed views remain empty. No generated IDs are copied from earlier requests.
Root-only paths are safe display metadata, excluded from module indexing. Null
filenames produce parser diagnostics. Duplicate parameter names are rejected by
feature validation. These fixes preserve existing public JSON fields.
See FINAL_REVIEW.md for the implementation review and INTEGRATION_GUIDE.md for usage.

## Code Manager input boundary
CodeManagerInputAdapter normalizes external ID spelling and attaches an explicitly
supplied revision before service validation. This component is stateless and lives
beside InputValidator in src/flowbridge_analysis/. It uses the existing validation
rules and preserves complete snapshots, including files sharing a basename.


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
