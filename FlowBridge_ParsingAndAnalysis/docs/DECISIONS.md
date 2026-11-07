# Decisions

## D027 — procedural module views and integration review (2026-11-06)

Decision: incorporate Harsha's procedural-CFG update in the requested reviewed
merge. Extend graphType with `module`, preserving existing input fields, JSON
keys, project/file IDs, revision scoping, and source-coordinate conventions.
File overviews remain structural; a separate module graph carries bounded
top-level flow. Function definitions navigate to existing function graphs.
This supersedes the module-execution deferral in D008/D023.

Rationale: scripts with executable statements need a view of their control flow;
joining independent function bodies with ordinary edges would misrepresent it.
Consumers must recognize the new graph type and tolerate an absent unreachable
normal End node. Module calls are lexical candidates, not a runtime-order proof.
Exception edges are limited to protected operations/handler bodies. Supported
try/loop-else metadata is traversed; omitted try clauses/aliases keep incomplete
scope diagnostics. Full Python semantics and source execution remain excluded.

Review corrections preserve the bounded subset: reject returns anywhere outside
functions, avoid guessed call targets in incomplete scopes, and commit each
file's analysis only when its graph construction succeeds. Retain a failed file
view and useful sibling results on failure. No new wire fields or dependencies.

Entries D001–D016 are dated 2026-10-29; later entries carry their own dates. Required choices come from the supplied master prompt;
provisional choices are recommendations, not finalized integration agreements.

## D001 — in-memory analysis only (required)
Decision: no analysis database; full snapshot per request.
Rationale: current workflow is upload/analyze/view; saved workspaces are deferred.
Consequences: no shared mutable revision cache; serializable results remain extensible.
Alternative deferred: SQL-backed saved analyses and incremental parsing.

## D002 — source parsing without execution (required)
Decision: use standard-library ast on fileContent, never execute/import uploads.
Rationale: source is untrusted and static analysis does not require execution.
Consequences: runtime call targets may remain unresolved.
Alternative rejected: introspection through running uploaded modules.

## D003 — one canonical result (required)
Decision: derive FlowchartOutput and MappingOutput from ProjectAnalysis.
Rationale: Kevin and Grace must share IDs and source data.
Consequences: output adapters cannot independently regenerate IDs.
Alternative rejected: separate graph generation pipelines for each consumer.

## D004 — documentation-first empty baseline (observed)
Decision: create documentation only in the first task.
Rationale: explicit first-task instruction; workspace has no implementation or starter.
Consequences: there is nothing to rewrite or test as Python; starter conflicts are
unknown, not absent by proof. Alternative rejected: inventing starter capabilities.

## D005 — validation details (provisional)
Decision: use defaults specified in INPUT_OUTPUT_CONTRACT, preserving the required shape.
Rationale: precise validation needs rules for booleans, empty values and duplicates.
Consequences: test these rules before relying on them; discuss any input-shape change.
Alternatives: permissive coercion (risks identity changes), strict rejection of unknown
fields (reduces forward compatibility). Revision type/range still needs teammate confirmation.

## D006 — partial results and unsupported scopes (provisional)
Decision: isolate failures, report graph status, use empty non-executable graphs for
unsupported function scopes, and retain valid sibling results.
Rationale: avoid misleading flow while retaining navigation metadata.
Consequences: consumers must inspect status; diagnostics carry affected scope/graph.
Alternative: omit affected graphs entirely (requires nullable function graph links).

## D007 — stateless diagnostics API (provisional)
Decision: return diagnostics on results; defer no-argument collect_diagnostics().
Rationale: a last-result service cache risks cross-request/revision contamination.
Consequences: suggested API is not promised verbatim; settle before implementation.
Alternative: a request-scoped collector, if later integration requires it.

## D008 — bounded semantics (provisional)
Decision: function CFGs initially abstract expressions; file views are overviews,
not module runtime CFGs. Implement conservative try/except and bounded import
resolution only in later tested phases.
Rationale: complete Python semantics exceed the current capstone scope.
Consequences: explicitly diagnose unsupported constructs and explain approximation.
Alternative: broad silent best-effort modeling (rejected for misleading graphs).

## D009 — starter as inspiration and modular scaffold (user requested)
Decision: retain the supplied starter under reference/flowbridge_starter; create
the requested src, tests and examples structure in the existing workspace root.
Rationale: the user explicitly requested inspiration rather than adopting the ZIP.
Consequences: archive instructions are reference content, module files are clearly
unimplemented, and starter outputs are not golden fixtures. Bytecode is omitted.
Alternative rejected: copying the monolithic starter into the active package.
This local reference extraction does not add ZIP intake to the analysis module.

## Open design items (remaining)
Single-file API, resource limits, path normalization,
module/package ambiguity handling, and exact exception subset need review when
their phases begin. No finalized input contract change has been made.

## D010 — model foundation (2026-10-29, current task)
Decision: implement documented validation defaults and typed records without
changing JSON keys. FileInput holds source; FileMetadata names the documented
FileInfo output record. ValidationResult returns a complete input or diagnostics;
direct model misuse raises ValueError (TypeError for missing constructor fields).
Rationale: explicit request for typed models and validation, without AST parsing.
Consequences: models do not imply working analysis or downstream projections.
Unknown extension fields must contain JSON data before being ignored. These
implemented defaults do not claim external teammate sign-off.
Alternatives: untyped dictionaries or an external framework were not needed.

## D011 — deterministic IDs (2026-10-29, current task)
Decision: URL-safe base64 encoding of versioned JSON tuples containing project,
revision, kind and structural key; sorted JSON keys for deterministic serialization.
Rationale: no shared counters or ambiguous delimiters; no hash collisions.
Consequences: callers must choose unique structural keys; IDs may be long, are
not secret and change with revision. Supplied project/file IDs remain intact.
Alternative: hashing is shorter but introduces theoretical collision risk.

## D012 — working rules (2026-10-29, current task)
Decision: adopt the user's twelve mandatory rules in AGENTS.md, including exact
precedence, required reads, evidence, documentation and final reporting.
Rationale: the obsolete first-task documentation-only restriction conflicts with
the current implementation request; it was explicitly removed.
Consequences: no approved architecture was silently replaced. Future tasks use
PROGRESS for actual status rather than relying on conversation history.

## D013 — parsing versus feature support (2026-10-29, current task)
Decision: parse with ast.parse only, return a separate internal ParseResult, and
inspect accepted ASTs with FeatureValidator in validator.py. Initial statements
are direct FunctionDef plus Assign, Expr, If and Return in function bodies.
Nested conditionals are accepted; nested functions and module execution remain
unsupported per the existing scoped design. A leading module docstring is metadata.
Rationale: the user requests syntax/feature separation and an explicit small subset.
Consequences: loops and try/except are parseable but unsupported, and no graphs
are generated. Expression children and signatures are inspected with an allowlist;
unsupported subtrees are reported once, with other branches still checked.
Alternative rejected: treating every successfully parsed AST as fully supported.

## D014 — diagnostic spans and parser limits (2026-10-29, current task)
Decision: copy AST byte offsets; normalize SyntaxError character offsets using
the original line prefix's UTF-8 length. Preserve point spans and return null
when no reliable start is available. Encoding and recursion failures have separate
codes and undetermined syntax_valid rather than being mislabeled syntax errors.
Rationale: frontend source coordinates must be consistent without invented ranges.
Consequences: ast.parse acceptance does not promise complete compiler context checks
or runtime validity; resource limits/process isolation remain a future task.
Alternative rejected: executing or dynamically importing uploaded code to validate it.

## D015 — lexical metadata without CFGs (2026-10-29, current task)
Decision: ASTAnalyzer consumes the parsed AST, exact FileInput and RevisionIds;
returns a file-local ASTAnalysis with FunctionInfo, SymbolTable and unresolved
CallSite records. Reuse existing FunctionInfo/SymbolInfo downstream shapes.
Rationale: explicit request for metadata, lexical bindings and calls without CFGs.
Consequences: graph IDs are reserved only; no graph references or ProjectAnalysis
are generated yet. Header defaults/decorators belong to the defining module scope;
annotation text is retained without asserting evaluation or annotation call sites.
Alternative rejected: walking all AST nodes without scope boundaries, which would
attribute nested declarations and header calls to the wrong function.

## D016 — conservative binding lookup (2026-10-29, current task)
Decision: retain every occurrence per scope/name and return nearest lexical groups,
not runtime targets. Nested/conditional/async/class declarations bind a name but
omit inner metadata/bodies. Unsupported subtrees mark extraction incomplete;
global/nonlocal causes the owning function body to be omitted. Do not fall back
through incomplete scopes. Imports are informational, never dynamically imported.
Rationale: avoid scope leakage and false name-only call resolution while implementing
the requested initial symbol table. Local assignments shadow parents regardless
of their execution order, but no initialization or reachability is inferred.
Consequences: conservative omissions can suppress valid outer-name candidates;
closures, definite assignment and full Python resolution remain future work.
Alternative rejected: silently choosing the last binding or a matching project name.

## D017 — class-aligned files (2026-11-03, user requested)
Decision: PascalCase component files; individual serializable model files with
package re-exports; retain existing class names and JSON contracts. Move feature
inspection to FeatureValidator.py, retaining function-only JSON validation in
validator.py. Legacy component paths alias canonical modules.
Rationale: align navigation with the supplied UML filename list without redesign.
Alternatives: rename classes to diagram terminology or introduce empty output
classes (rejected); remove old import paths (rejected to preserve public APIs).
Consequences: model dependency imports are explicit and acyclic; no duplicated
implementations. Scaffolds remain unimplemented. Complete mapping is recorded in
FILE_ORGANIZATION.md; actual UML images were not available in this task.

## D018 — input-validation class and preserved ID format (2026-11-03)
Decision: rename validator.py to InputValidator.py and expose stateless
InputValidator.validate(payload). Keep validate_project as the single existing
validation implementation and preserve old module imports through an alias.
Rationale: explicit Phase 1 request and class-aligned navigation, without behavior
or JSON changes. Input validation never parses source; PythonParser owns syntax.
Alternative: duplicate/rewrite validation inside the class (rejected as unnecessary).
RevisionIds retains fb1_ JSON/base64 encoding; clearer scope documentation and tests
are sufficient. Random IDs or a new encoding would break determinism/compatibility.
Consequences: same supplied identifiers, same diagnostics and generated IDs;
callers remain responsible for unique structural keys within each owning context.

## D019 — Phase 2 graph fields and model integrity (2026-11-03)
Decision: honor the user's explicit graphType and optional edge label requirements:
GraphModel stores graph_type and serializes graphType; FlowEdge stores nullable
label. Preserve view_type as a Python constructor/property alias with conflict
checks. Retain file/function owners, graph status, enum values and ID encoding.
Rationale: the new explicit request takes precedence over the prior viewType JSON
spelling. This output change was explained before implementation; it does not
change the input contract. Exact UML images remain unavailable.
Alternatives: silently retaining viewType would miss the request; emitting both
JSON keys adds redundant contract state; breaking all Python callers unnecessarily
would require unrelated CFG edits. These alternatives were rejected.
Consequences: existing JSON consumers must migrate to graphType. Python callers
remain compatible. dataclasses.replace should use canonical graph_type when changing
the graph kind. Nested records are revalidated, references use graph-local tuple
keys, duplicate mappings and inconsistent call ownership are rejected. No parsing,
CFG construction, output adapter or new supporting relationship schema was added.

## D020 — parsing identity and bounded loop metadata (2026-11-03)
Decision: ParseResult carries file_id for successful, empty and failed parses;
this optional trailing Python-only field preserves earlier constructor calls.
FeatureValidator uses named traversal context rather than six-position tuples,
without changing its allowlist or conservative exception semantics.
ASTAnalyzer visits ordinary for/while targets, tests and bodies in their existing
scope, including calls and assignments, and treats break/continue as nonbinding.
Loop-else and try binding subtrees remain omitted with INCOMPLETE_SCOPE. Nested
functions/classes/expression scopes remain isolated. Symbol lookup detects cycles
in externally mutated parent chains instead of looping forever.
Rationale: the user's Phases 3/4 require identity-preserving results and useful local
bindings/calls. Python loops do not introduce a new scope. Lexical occurrence does
not imply execution or definite assignment, even for while False.
Alternatives: treating every loop as incomplete loses supported metadata; inferring
runtime reachability or implementing nested scopes exceeds this bounded phase.
Consequences: loop bindings can now shadow outer names; source/ID/JSON contracts and
CFG algorithms are unchanged. Full Python scope/compiler semantics remain unclaimed.
This refines D016's earlier conservative omission of all loop subtrees.

## D021 — loop-else distinguishes exhaustion and break (2026-11-03)
Decision: implement loop-else as explicitly requested in Phase 5B. Only the loop
header's false/exhaustion path enters else; saved break paths bypass it. Pop the
loop body context before building else. Feature validation mirrors this context
boundary, allowing inner-else controls only when an outer loop body exists.
Rationale: Python's else means normal completion, not a common destination for all
loop exits. A separate list of break exits already provides the required distinction.
Alternatives: route break through else (incorrect), or keep rejecting all loop-else
(unnecessary now that distinct completion paths are tested).
Consequences: existing source without loop-else keeps its topology/ID conventions;
else statements gain normal source mappings. Return/exception paths bypass else.
No input/output schema changes. ASTAnalyzer loop-else extraction remains a separate
incomplete milestone; async iteration and full exception/finally handling remain
unsupported. This supersedes the original loop-else deferral for CFGs only.

## D022 — bounded call relationships (2026-11-03)
Decision: implement requested call resolution ahead of service assembly. Preserve
CallReference/callReferences as the canonical public contract; CallRelationship
is a Python alias. Add internal ImportRelationship metadata rather than inventing
new downstream fields. Resolve lexical declarations and explicit absolute module
imports using root-relative snapshot paths. Reject uncertain scope/import patterns.
Rationale: distinguish module imports from member imports without source execution
or ambiguous flattened importTarget interpretation. Alternatives rejected: searching
the entire project by function name, runtime importing, or changing public JSON.
Consequences: graph IDs remain reserved until assembly; runtime monkey-patching,
relative/local imports and re-exports remain outside the subset. Full UML images
remain unavailable; the existing approved contract controls public field names.

## D023 — hierarchy and approved projection extension (2026-11-03)
Decision: implement structural project/file views and request-local service assembly.
Project/file graphs contain navigation nodes without execution edges (D008). Failed
parses retain empty failed file graphs; unsupported module execution retains a
complete structural overview and unsupported FileMetadata status. Unsupported
function CFGs remain empty but navigable. Empty valid projects succeed.
Rationale: preserve useful sibling views without asserting module execution flow.
Alternative rejected: connecting independent functions with ordinary CFG edges.

The user explicitly approved adding files, functions, callReferences and symbols
(including import bindings) to FlowchartOutput. This gives Kevin labels/ownership,
call targets and import metadata alongside graphs. MappingOutput already contains
graphReferences and callReferences; its fields remain unchanged. The UML role
CallRelationship remains the alias of CallReference; no callRelationships rename or
new public importRelationships array is introduced. Exact UML images remain absent.
Alternative rejected: silently adding duplicate relationship fields. Both outputs
are immutable-at-capture JSON snapshots of one validated ProjectAnalysis; no new
IDs, persistence or independently built graphs are introduced by projections.

## D024 — final review corrections and revision lifecycle (2026-11-03)
Decision: retain full-snapshot stateless reanalysis and compatibility for both
ProjectGraphs/ProjectGraphResult names and list/dictionary function-graph inputs.
Reject invalid duplicate parameters before executable CFG construction; return
structured null-filename diagnostics; tolerate root-only metadata paths without
filesystem operations. Strict JSON failure-envelope decoding preserves valid
revision identity consistently for text/dictionary inputs.
Rationale: observed import failures and input-triggered defects, verified with
regression tests. Alternatives rejected: reusing previous valid graphs on syntax
failure, broad exception suppression, silently changing consumer schema or input
path requirements. Consequence: latest-response selection stays with the UI;
callers must issue distinct revision IDs for changed text. Full compiler/resource
validation remains explicitly incomplete. No public schema changes in this task.

## D025 — Code Manager input adapter (user approved)
Decision: accept projectID/fileID through CodeManagerInputAdapter.normalize and
translate to existing canonical names, adding the caller-supplied revision_id.
Rationale: actual Code Manager output has uppercase ID keys and no revision field.
Preserve backend/consumer contracts and source text. Reject alias/revision conflicts.
Alternative rejected: implicit adapter counters/default revision 1, which would
misidentify snapshots across workers or restarts. The backend owns revision ordering;
the local example runner exposes --revision-id. No database or cached results added.

## D026 — absolute imports are supported metadata
User clarified that supported imports must participate in symbol-based call
resolution without unsupported-feature errors. Accept direct absolute imports in
FeatureValidator while retaining structural file views. Previously the blanket
module-execution rejection contradicted the supported call-resolution subset.
No public schema change or runtime importing. Relative/star/future/conditional/local
import forms retain explicit restrictions. Missing targets remain nonresolved.
