# Python parsing and feature support

## Separate stages
PythonParser.parse(FileInput) calls ast.parse(source, filename=path, mode='exec').
The mode selects module grammar; it never executes uploaded code or reads that path.
ParseResult contains an internal AST, syntax_valid, diagnostics and file_id. True means parser
acceptance, False means SyntaxError (including indentation errors), and None means
encoding/recursion failure prevented a decision. ASTs never enter public JSON.
Parser acceptance is not complete compiler/runtime validation (e.g. ast.parse may
accept a module return or duplicate parameter names).

FeatureValidator.validate(ast.Module, file_id) inspects an accepted AST separately.
FeatureValidationResult.is_supported is true when there are no error diagnostics;
warning-only conservative exception modeling is supported within its stated limits.
Unsupported features never change syntax_valid or destroy the AST. Call the feature
validator only after a successful parse. CFGBuilder uses it before emitting paths.

## Current supported subset
Direct FunctionDef at module level; module/function Assign, AnnAssign, AugAssign,
Expr, Pass, If/elif/else, For, While, Break, Continue, and bounded Try/ExceptHandler.
Return is allowed only inside functions, including inside their containers. Empty files,
comments and a leading module docstring are accepted. Break/continue require a loop.
For/while else is supported. Nested function definitions are unsupported.

Try must be non-nested, have handlers, and have neither else nor finally. Handler
types are names/tuples of names or a final bare except. Aliases, try-star, explicit
raise and dynamic handler-type expressions remain unsupported. Accepted tries emit
CONSERVATIVE_EXCEPTIONS warnings because matching is approximate. See CFG_DESIGN.md.

Ordinary signatures/defaults/annotations are inspected without evaluation. Decorators
and generic type parameters remain unsupported. Expressions include names, literals,
arithmetic/boolean/comparison operations, calls, attributes/subscripts/slices, literal
containers, unpacking, conditional expressions and f-strings. All expression children
are checked. Comprehensions, lambda, walrus, yield and await cannot hide in statements,
arguments, defaults or annotations. Expressions remain atomic in statement CFGs.

Direct absolute imports are supported as metadata and statement nodes in module
CFGs; no imports are executed. Relative/star/future/conditional/local imports,
classes/async, with/match, assert, del, global/nonlocal, and all unlisted constructs
remain unsupported. Direct eval/exec/compile calls receive unsupported diagnostics.

Files with supported top-level executable statements get a separate graph with
`graphType: module`. File views remain structural overviews. Function definition
nodes in a module CFG link to the corresponding function graph rather than
inserting its body. An unreachable normal End node is omitted. Exception edges
are expanded for protected operations and handler bodies, not arbitrary statements
outside a try. This is a bounded approximation, not runtime simulation.

## Explicit inspection algorithm
A local stack visits AST children in source order, carrying module/function scope,
loop depth and try depth. Function entry resets context. Loop depth checks legal
break/continue ownership; try depth rejects nested exception handling. Each ordinary
node must match an explicit allowlist; unknown nodes fail closed. An unsupported
subtree gets a root diagnostic and is skipped to avoid cascades; other branches and
functions are still inspected, including structurally unreachable statements.

Diagnostics use severity error/code UNSUPPORTED_FEATURE with file/source context
and a scope description. The standalone validator leaves graphId null; CFGBuilder
adds the affected graph ID. The input AST is unchanged and no visitor state persists.
Feature support and symbol-table completeness remain different: lexical extraction
traverses supported try and loop-else subtrees. Omitted try else/finally clauses
and unsupported exception aliases mark their scopes incomplete and prevent
confident call-target resolution.

## Coordinates and failures
AST offsets are copied as UTF-8 bytes. SyntaxError character offsets are converted
by encoding the source line prefix. CRLF/CR is normalized for line lookup, not source
storage. EOF offsets are anchored at line end; unknown starts give null locations;
missing/reversed ends use a point at the reliable start. Point errors are preserved.
SYNTAX_ERROR, INVALID_SOURCE_ENCODING and PARSER_LIMIT remain separate codes.
No process isolation, upload size/time limits or full compiler validation is implied.

## Tests
Parser tests cover syntax/indentation/NUL/Unicode errors, positions, recursion failure,
reuse and no source side effects. Feature tests cover allowlisted nested statements,
unsupported signatures/expressions/scopes and syntax/support separation. CFG tests
exercise the newly accepted loops, pass and bounded exception handling end-to-end.
The CFG milestone passed 113 tests; TESTING.md records the current suite and commands.

## Requested Phase 3 verification — 2026-11-03
Existing parser and allowlist already covered the requested language subset.
PythonParser now retains the exact file ID in ParseResult even when there is no
diagnostic. Paths are passed as AST filename metadata, never opened/imported.
Named _Visit records make enclosing function, loop depth and try depth explicit;
children get their own context so siblings cannot inherit a preceding loop's depth.
No feature/CFG semantics were expanded. Basic try/except remains the previously
implemented conservative subset, with CONSERVATIVE_EXCEPTIONS on accepted tries.
Class declarations and nested functions remain unsupported-feature diagnostics.

Parsing answers: can ast.parse build a syntax tree? For example, `class C: pass`
parses successfully. Feature validation answers: does FlowBridge support that tree?
It rejects the class with UNSUPPORTED_FEATURE. `def broken(:` instead fails parsing
with SYNTAX_ERROR. Neither stage executes the source, infers runtime names, or
claims complete compiler validation. Empty files parse and validate successfully.
The new multi-file test continues through a syntax-invalid sibling and checks
supported, empty and class-unsupported files separately. See TESTING.md.

## Phase 5B feature validation
Loop body nodes use enclosing loop depth plus one; header and else nodes use the
original enclosing depth. Thus break/continue in a top-level loop else is rejected,
while an inner loop else can control its enclosing outer body. Sibling contexts
remain independent and unsupported constructs inside else still fail preflight.
This permits ordinary loop-else CFGs without broadening async/finally semantics.

## Final review parsing clarification
Null filename metadata yields INVALID_SOURCE_PATH with syntax_valid=None instead
of raising ValueError. Duplicate parameter names accepted by ast.parse are rejected
by FeatureValidator as UNSUPPORTED_FEATURE; their CFGs are empty/unsupported.
This bounded check does not imply complete Python compiler-context validation.


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
