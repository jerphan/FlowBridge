# CFG design and implemented semantics

November 8 extension (D028): `build_module` provides the top-level module graph,
and `build_file` provides file execution with bounded same-file call expansion.
Expansion requires a resolved CallReference and has a recursion guard. Returned
calls terminate their caller after the callee completes; unresolved/shadowed
calls remain atomic. Cross-file calls use navigation references to function
graphs. Original graph/node IDs and source spans remain shared across consumers.

## API and scope
`CFGBuilder.build(function, file_input, ids) -> CFGResult` accepts a direct module
FunctionDef from PythonParser, the exact FileInput snapshot and RevisionIds.
CFGResult contains graph (GraphModel), source_mappings and diagnostics. This is
function CFG construction only; separate components now provide project/file
overviews, call resolution and full service orchestration. Uploaded source is never run.

The builder uses the same file/definition-position/name key as ASTAnalyzer for
functionId and graphId. Node/edge IDs add graph identity and request-local counters.
IDs are deterministic for identical snapshots, unique within the graph, and change
with revision. No state lives on the public builder or leaks across builds.

Before building, FeatureValidator checks the whole function, including unreachable
code. Any error produces an empty graph with status unsupported and no mappings.
Diagnostics identify file, graph and AST span. Recursion failure produces an empty
failed graph with CFG_LIMIT, discarding partial work. Programmer errors (wrong AST
argument type or mismatched inputs) are not treated as uploaded syntax diagnostics.
The caller must supply the AST from the exact snapshot; source matching is not inferred.

## Predecessor strategy, step by step
A pending predecessor is `(node_id, edge_type)`: a path whose next normal node is
not known yet. A block consumes a list of these paths and returns only surviving
normal exits. This is a recursive structured-block traversal, not a general graph
fixed-point solver or runtime evaluator.

1. Create synthetic Start and End. Start is the initial pending predecessor.
2. A sequential statement receives edges from every pending predecessor, then
   becomes the only new normal predecessor.
3. If creates a condition node and builds true/false blocks independently. Missing
   else is an empty block that preserves its false predecessor. Combine surviving
   exits: the following statement is their join, without requiring a separate node.
4. Return connects to End and returns an empty predecessor list. It never joins
   a later statement. Both branches returning therefore make the following block
   structurally unreachable.
5. When a block has no predecessors, warn UNREACHABLE_STATEMENT and omit each
   following executable statement. Preflight still rejects unsupported constructs
   there; the builder does not silently forgive unsupported syntax after return.
6. Connect any final normal predecessors to End for implicit function completion.

Assign, Expr and Pass create statement nodes. Pass is a source-backed no-op.
If/elif/else and nested conditionals preserve branch labels. Expressions are atomic:
short-circuit, comparison chains and conditional-expression internals are not
expanded into subgraphs. Source order is not constant evaluation. Except for literal
boolean while tests, no constant folding/path feasibility analysis is performed.

## Loops and terminated paths
Each active loop pushes a context containing its header and a list of pending
break exits. The nearest context owns break/continue, including inside try handlers.

- While evaluates its test at a loop header. True enters the body; false exits.
  Literal while True has no false exit, and literal while False omits body nodes
  with unreachable diagnostics. An infinite loop can leave the synthetic End
  unreachable; its presence does not imply a path to it.
- For separates one-time `Iterate: expression` setup from `Next: target`. The latter
  abstracts iterator advancement and target binding. True enters the body; false
  means normal exhaustion. Back/continue edges never re-evaluate the iterable.
- Normal body exits connect to a synthetic `Loop back` latch preserving any pending
  true/false labels; the latch has a back edge to the header.
- Continue connects directly to the nearest header with a continue edge and returns
  no normal exits. Break adds a deferred break predecessor to its loop's exit list
  and returns no body fallthrough. Neither reaches the rest of its body block.
- Normal false/exhaustion enters the loop else suite, if present. Break exits
  bypass that suite. Its surviving normal exits join break exits at the successor.
  A return exits the function and never enters else, the latch or the successor.
- The loop context is popped before else is built. Controls in an inner loop else
  can target an outer body; without an outer loop, they are rejected by preflight.

## Basic try/except: conservative may-flow
Supported: non-nested try with one or more ordinary except handlers, without else
or finally. A handler type is a Name or tuple of Names, or a final bare except.
No exception aliases (`as error`): their mandatory cleanup on every exit is not yet
modeled. Explicit raise, try-star, nested try (including in handlers), dynamic handler
types, finally and try/else are rejected with UNSUPPORTED_FEATURE.

Every supported try emits CONSERVATIVE_EXCEPTIONS, a warning that types are not
inferred. Graph status complete means complete for this documented abstraction,
not precise Python exception analysis. Warning diagnostics must accompany the graph.

- Protected operations can send an exception edge to a synthetic dispatch node.
  Dispatch enters the first handler test. A typed handler's true path runs its body;
  false proceeds to the next test. A bare handler accepts the remaining path.
- A final unmatched typed handler reaches an `Unhandled exception` node and then
  Exceptional End through an unhandled edge. Handler-type lookup/validation can
  itself fail and has an exception edge to Exceptional End, even if a later bare
  handler exists. Ordered possible matches do not assert which exception type occurs.
- Successful protected completion bypasses all handlers. Only surviving normal
  body/handler exits join the next statement.
- Handler operations run outside the protected dispatch context. Their failures
  go outward (to Exceptional End in this non-nested subset), never sibling handlers.
- In functions containing try, a valued return first uses `Evaluate return: expr`
  (with an exceptional alternative), then a terminal return node. Only evaluation
  can enter a handler; the return-transfer node has exactly its return edge to End.
  A bare return has no evaluation or exception alternative.
- Break/continue keep their loop targets and do not become handler paths.
- If the protected body has no modeled raising operation (e.g. pass or bare return),
  omit handlers, remove the unused dispatch and warn UNREACHABLE_HANDLER.

Assignments, expression statements, conditions, iterator setup/advancement and
return-value evaluation are conservatively treated as possibly raising. This can
include operations that are safe in a particular program. For StopIteration at
iterator advancement, false is normal exhaustion; the exception edge represents
other possible failures. Target-binding errors share that exceptional alternative.

When a function contains try, operations outside its protected blocks also have
exception edges to Exceptional End. Functions without try model ordinary control
flow only; implicit exceptions are not expanded. No exception type inference,
asynchronous signal modeling or expression-internal paths are claimed.

## Locations, mappings and IDs
Nodes get AST positions at creation, never by parsing labels. Sequential/return/
break/continue nodes use statement spans; condition and while headers use tests;
for setup uses the iterable expression and its next header uses the target span.
Handler nodes use the ExceptHandler span. Return-evaluation nodes use the expression
span, so overlapping mappings with the return statement are intentional.
Start/End, latches, dispatch and unhandled routing nodes are synthetic and unmapped.
Every source-backed node has exactly one SourceMapping referencing its graph/node.
Lines are one-based; columns are zero-based UTF-8 bytes; ends are exclusive.

## Unsupported semantics and component boundaries
Classes, async/generators, nested functions, decorators/generic functions, imports,
with/match, comprehensions/lambda/walrus, global/nonlocal, annotated/augmented
assignment and other unlisted statements remain feature-unsupported. No construct
is silently converted to an ordinary sequential node.
ASTAnalyzer still conservatively omits try/loop-else binding subtrees and marks lexical
scopes incomplete. Supporting a CFG does not make lexical/call analysis complete.

## Validation evidence
Incremental runs: 90 tests after sequences/branches; 99 after loops; 113 after
basic exceptions/integration. The 33 CFG tests cover joins, nested/empty branches,
early returns, unreachable statements, loop exits/back edges, nearest break/continue,
for setup once, boolean while behavior, handler ordering/bypass/failure, return
expression errors, unsupported semantics, ID/mapping integrity and revised snapshots.
The final suite passes on Python 3.12.14. See TESTING.md for commands and results.

## Phase 5A — sequence/condition/return verification (2026-11-03)
These algorithms already existed. The worker now separates build_if and build_return
from statement dispatch, with block remaining the sequence helper. Comments explain
pending branches, implicit joins and terminal exits. Node creation immediately
attaches AST spans and mappings; the ID format and creation order are unchanged.
No loop or exception algorithm was introduced or changed.

Example:
```python
def choose(x):
    if x:
        y = 1
    else:
        y = 2
    return y
```
Exact paths: Start --next--> x; x --true--> y = 1; x --false--> y = 2;
each assignment --next--> return y; return y --return--> End.
The return node is the join for both assignment paths. It has no outgoing next
edge. If one branch returns early, that branch contributes no pending exit and
only the other branch reaches the following statement. If both return, following
statements are diagnosed as unreachable and have no nodes or mappings.

An omitted else is an empty AST statement list and retains the false predecessor.
Python does not permit a textually empty else suite; `else: pass` instead creates
a mapped no-op node. elif is an If in the preceding If's orelse list. Nested
conditions recurse through the same branch helper; labels need not be unique.
The new tests compare complete edge multisets identified by label and source line,
so repeated labels cannot hide incorrect connectivity or duplicate edges.
Expression-internal control flow and constant-condition feasibility remain outside
this abstraction. Unsupported unreachable syntax is still rejected by preflight.

## Phase 5B — loop completion and loop-else (2026-11-03)
Existing while/for headers, back edges and nearest-loop contexts are preserved.
build_loop_control now explains continuation versus deferred break destinations.
Each _Loop context holds a header and pending break exits. The body is built while
that context is active. Normal body exits go through the Loop back latch; continue
goes directly to the condition (while) or advancement node (for). For iterable setup
runs once. Return contributes no loop continuation.

After the body, pop the context and send only false/exhaustion through orelse.
Then combine surviving else exits with saved breaks. This separation ensures a
break never enters its own else. An empty else preserves the original false edge.
Zero iterations can enter else; while False omits its body and enters else.
while True has no normal exhaustion: its else is diagnosed unreachable, even if
a break makes the following statement reachable. Return or an exception bypasses
else. Break/continue inside an inner loop's else belongs to an enclosing loop body;
it is unsupported without an enclosing body. A new loop inside else has its own
normal context. FeatureValidator uses the same body/else depth distinction.

Example: `for item in items: use(item)` followed by `else: exhausted()`:
Start -> iterator setup -> advancement; advancement true -> use(item) -> latch
--back--> advancement; advancement false -> exhausted() -> successor. A break in
the body instead has a break edge to the successor, bypassing exhausted().

The AST For/While node describes syntax: target/iterable or condition, body and
orelse. It contains the body once, not an edge for every runtime iteration. The CFG
adds back edges to express repetition and explicit exits for exhaustion/break.
No source is executed to discover those paths. General condition feasibility,
async iteration and full exception semantics remain outside the supported subset.
ASTAnalyzer still marks loop-else binding extraction incomplete; CFG support does
not imply complete lexical/call analysis. No JSON fields or edge enums changed.

## Phase 5C verification — 2026-11-03
The existing exception algorithm already implements the requested bounded subset;
no exception production algorithm changed in this task. New regressions verify the
complete edge set for successful/exceptional bare-handler paths and fail-closed
nested try inside a handler. Existing tests cover multiple ordered handlers,
return evaluation/transfer, handler failures, loop interactions and rejected forms.
Supported exactly: non-nested ordinary try/except, one or more Name/tuple-of-Names
handlers and optional final bare handler, normal continuation, return, and supported
loop controls. Exceptions are conservative may-flow edges, not runtime type proofs.
Finally, try-else, nested try, aliases, explicit raise, dynamic handler types and
except-star remain unsupported with diagnostics and empty unsupported graphs.


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
