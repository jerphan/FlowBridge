"""Statement-level CFG construction from pending normal predecessors."""
import ast
from dataclasses import dataclass, field, replace

from .RevisionIds import RevisionIds
from .models import (CallReference, Diagnostic, EdgeType, FileInput, FlowEdge, FlowNode,
                     FunctionInfo, GraphModel, GraphReference, NodeType, SourceMapping)
from .PythonParser import ast_location
from .FeatureValidator import FeatureValidator


@dataclass
class CFGResult:
    """A function graph and its mappings/diagnostics, never an AST JSON payload."""
    graph: GraphModel
    source_mappings: list[SourceMapping] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    graph_references: list[GraphReference] = field(default_factory=list)


# A pending path is a node plus the edge label to use when its successor is known.
Predecessors = list[tuple[str, EdgeType]]


@dataclass
class _Loop:
    """Active body continuation target and deferred breaks that bypass its else."""
    header: str
    breaks: Predecessors = field(default_factory=list)


class CFGBuilder:
    """Build a fresh graph for a direct module-level function and its source snapshot."""

    def build(self, function: ast.FunctionDef, file_input: FileInput, ids: RevisionIds,
              local_functions: dict[str, ast.FunctionDef] | None = None,
              functions_by_id: dict[str, FunctionInfo] | None = None,
              call_references: list[CallReference] | None = None) -> CFGResult:
        """Validate the entire function before constructing executable paths."""
        if not isinstance(function, ast.FunctionDef):
            raise TypeError('CFGBuilder requires an ast.FunctionDef')
        file_input.__post_init__()
        worker = _FunctionBuilder(function, file_input, ids,
                                  local_functions=local_functions,
                                  functions_by_id=functions_by_id,
                                  call_references=call_references)
        features = FeatureValidator().validate(ast.Module(body=[function], type_ignores=[]), file_input.file_id)
        diagnostics = [replace(item, graph_id=worker.graph_id) for item in features.diagnostics]
        if function.col_offset != 0:
            diagnostics.append(worker.diagnostic(function, 'UNSUPPORTED_FEATURE',
                                                  'Only direct module-level functions have CFGs.'))
        if any(item.severity == 'error' for item in diagnostics):
            return CFGResult(worker.graph('unsupported'), diagnostics=diagnostics)
        worker.diagnostics.extend(diagnostics)
        try:
            return worker.build()
        except RecursionError:
            # No partial graph escapes if recursive block construction hits a limit.
            return CFGResult(worker.graph('failed', empty=True), diagnostics=[worker.diagnostic(
                function, 'CFG_LIMIT', 'Function exceeds CFG construction recursion capacity.')])

    def build_module(self, tree: ast.Module, file_input: FileInput, ids: RevisionIds,
                     local_functions: dict[str, ast.FunctionDef] | None = None,
                     functions_by_id: dict[str, FunctionInfo] | None = None,
                     call_references: list[CallReference] | None = None) -> CFGResult:
        """Build a fresh execution CFG for top-level module statements."""
        if not isinstance(tree, ast.Module):
            raise TypeError('CFGBuilder.build_module requires an ast.Module')
        file_input.__post_init__()
        worker = _ModuleBuilder(tree, file_input, ids,
                                local_functions=local_functions,
                                functions_by_id=functions_by_id,
                                call_references=call_references)
        features = FeatureValidator().validate(tree, file_input.file_id)
        diagnostics = [replace(item, graph_id=worker.graph_id) for item in features.diagnostics]
        if any(item.severity == 'error' for item in diagnostics):
            return CFGResult(worker.graph('unsupported'), diagnostics=diagnostics)
        worker.diagnostics.extend(diagnostics)
        try:
            return worker.build()
        except RecursionError:
            return CFGResult(worker.graph('failed', empty=True), diagnostics=[worker.diagnostic(
                tree, 'CFG_LIMIT', 'Module exceeds CFG construction recursion capacity.')])

    def build_file(self, tree: ast.Module, file_input: FileInput, ids: RevisionIds,
                   local_functions: dict[str, ast.FunctionDef] | None = None,
                   functions_by_id: dict[str, FunctionInfo] | None = None,
                   call_references: list[CallReference] | None = None) -> CFGResult:
        """Build a fresh execution CFG for an entire file with function inlining."""
        if not isinstance(tree, ast.Module):
            raise TypeError('CFGBuilder.build_file requires an ast.Module')
        file_input.__post_init__()
        worker = _FileFlowBuilder(tree, file_input, ids,
                                  local_functions=local_functions or {},
                                  functions_by_id=functions_by_id or {},
                                  call_references=call_references or [])
        features = FeatureValidator().validate(tree, file_input.file_id)
        diagnostics = [replace(item, graph_id=worker.graph_id) for item in features.diagnostics]
        if any(item.severity == 'error' for item in diagnostics):
            return CFGResult(worker.graph('unsupported', empty=True), diagnostics=diagnostics)
        worker.diagnostics.extend(diagnostics)
        try:
            return worker.build()
        except RecursionError:
            return CFGResult(worker.graph('failed', empty=True), diagnostics=[worker.diagnostic(
                tree, 'CFG_LIMIT', 'File exceeds CFG construction recursion capacity.')])


class _FunctionBuilder:
    def __init__(self, function: ast.FunctionDef, file: FileInput, ids: RevisionIds,
                 local_functions: dict[str, ast.FunctionDef] | None = None,
                 functions_by_id: dict[str, FunctionInfo] | None = None,
                 call_references: list[CallReference] | None = None) -> None:
        self.function = function
        self.file = file
        self.ids = ids
        self.local_functions = local_functions or {}
        self.functions_by_id = functions_by_id or {}
        self.call_references = call_references or []
        self.calls_by_loc = {
            (c.location.start_line, c.location.start_column): c
            for c in self.call_references if c.file_id == file.file_id
        }
        key = (file.file_id, function.lineno, function.col_offset, function.name)
        self.function_id = ids.make('function', *key)
        self.graph_id = ids.make('graph', 'function', *key)
        self.nodes: list[FlowNode] = []
        self.edges: list[FlowEdge] = []
        self.mappings: list[SourceMapping] = []
        self.diagnostics: list[Diagnostic] = []
        self.graph_references: list[GraphReference] = []
        self.loops: list[_Loop] = []
        self.node_count = 0
        self.exception_target: str | None = None
        self.exceptional_end: str | None = None
        self.in_handler = False
        self.track_exceptions = any(isinstance(node, (ast.Try, ast.Raise)) for node in ast.walk(function))

    def graph(self, status: str, empty: bool = False) -> GraphModel:
        return GraphModel(graph_id=self.graph_id, view_type='function', status=status,
                          file_id=self.file.file_id, function_id=self.function_id,
                          nodes=[] if empty else self.nodes, edges=[] if empty else self.edges)

    def diagnostic(self, node: ast.AST, code: str, message: str, severity: str = 'error') -> Diagnostic:
        return Diagnostic(severity=severity, code=code, message=message, file_id=self.file.file_id,
                          graph_id=self.graph_id, source_location=ast_location(node, self.file.file_id))

    def node(self, kind: NodeType, label: str, source: ast.AST | None = None) -> str:
        """Allocate a graph-owned ID and attach its AST span/mapping immediately."""
        node_id = self.ids.make('node', self.graph_id, self.node_count)
        self.node_count += 1
        location = ast_location(source, self.file.file_id) if source is not None else None
        self.nodes.append(FlowNode(node_id=node_id, node_type=kind, label=label, source_location=location))
        if location is not None:
            self.mappings.append(SourceMapping(graph_id=self.graph_id, node_id=node_id, location=location))
        return node_id

    def edge(self, source: str, target: str, kind: EdgeType = 'next') -> None:
        self.edges.append(FlowEdge(edge_id=self.ids.make('edge', self.graph_id, len(self.edges)),
                                   source_id=source, target_id=target, edge_type=kind))

    def connect(self, incoming: Predecessors, target: str) -> None:
        for source, kind in incoming:
            self.edge(source, target, kind)

    def text(self, node: ast.AST) -> str:
        return ast.get_source_segment(self.file.file_content, node) or ast.unparse(node)

    def exception_end(self) -> str:
        if self.exceptional_end is None:
            self.exceptional_end = self.node('end', 'Exceptional End')
        return self.exceptional_end

    def operation(self, kind: NodeType, label: str, source: ast.AST,
                  incoming: Predecessors, may_raise: bool = True) -> str:
        current = self.node(kind, label, source)
        self.connect(incoming, current)
        can_raise = (self.exception_target is not None) or self.in_handler
        if self.track_exceptions and may_raise and can_raise:
            self.edge(current, self.exception_target or self.exception_end(), 'exception')
        return current

    def build(self) -> CFGResult:
        """Create synthetic endpoints and connect surviving body exits to End."""
        start = self.node('start', 'Start')
        self.end = self.node('end', 'End')
        remaining = self.block(self.function.body, [(start, 'next')])
        self.connect(remaining, self.end)
        if not any(edge.target_id == self.end for edge in self.edges):
            self.nodes = [n for n in self.nodes if n.node_id != self.end]
            self.mappings = [m for m in self.mappings if m.node_id != self.end]
        return CFGResult(self.graph('complete'), self.mappings, self.diagnostics, self.graph_references)

    def block(self, statements: list[ast.stmt], incoming: Predecessors) -> Predecessors:
        """Build a sequence, carrying only paths that can reach its next statement.

        An empty sequence preserves incoming branch labels. Once every path has
        terminated, diagnose remaining statements without emitting executable nodes.
        """
        for statement in statements:
            if not incoming:
                self.diagnostics.append(self.diagnostic(statement, 'UNREACHABLE_STATEMENT',
                    'No modeled normal path reaches this statement; executable nodes omitted.', 'warning'))
                continue
            incoming = self.statement(statement, incoming)
        return incoming

    def _find_call(self, statement: ast.stmt) -> ast.Call | None:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            return statement.value
        if isinstance(statement, (ast.Assign, ast.AnnAssign)) and isinstance(statement.value, ast.Call):
            return statement.value
        if isinstance(statement, ast.Return) and isinstance(statement.value, ast.Call):
            return statement.value
        calls = [n for n in ast.walk(statement) if isinstance(n, ast.Call)]
        if len(calls) == 1:
            return calls[0]
        return None

    def _top_nested_calls(self, node: ast.AST) -> list[ast.Call]:
        if isinstance(node, ast.Call):
            return [node]
        calls = []
        for child in ast.iter_child_nodes(node):
            calls.extend(self._top_nested_calls(child))
        return calls

    def _resolve_target(self, call: ast.Call) -> FunctionInfo | None:
        call_ref = self.calls_by_loc.get((call.lineno, call.col_offset))
        if call_ref and call_ref.resolution == 'resolved' and call_ref.target_function_id:
            return self.functions_by_id.get(call_ref.target_function_id)
        if isinstance(call.func, ast.Name) and call.func.id in self.local_functions:
            return next((f for f in self.functions_by_id.values()
                         if f.file_id == self.file.file_id and f.function_name == call.func.id), None)
        return None

    def build_call(self, statement: ast.stmt, call: ast.Call, incoming: Predecessors) -> Predecessors:
        target_fn = self._resolve_target(call)
        is_ret = isinstance(statement, ast.Return)

        if target_fn:
            for arg in call.args:
                for nested in self._top_nested_calls(arg):
                    if nested is not call:
                        nested_fn = self._resolve_target(nested)
                        if nested_fn:
                            nested_stmt = ast.Expr(value=nested)
                            incoming = self.build_call(nested_stmt, nested, incoming)

            node = self.node('function', self.text(statement), statement)
            self.connect(incoming, node)
            self.graph_references.append(GraphReference(
                source_graph_id=self.graph_id,
                source_node_id=node,
                target_graph_id=target_fn.graph_id,
            ))
            can_raise = (self.exception_target is not None) or self.in_handler
            if self.track_exceptions and can_raise:
                self.edge(node, self.exception_target or self.exception_end(), 'exception')

            if is_ret:
                self.edge(node, self.end, 'return')
                return []
            return [(node, 'next')]

        if is_ret:
            return self.build_return(statement, incoming)
        node = self.operation('statement', self.text(statement), statement, incoming,
                              may_raise=not isinstance(statement, ast.Pass))
        return [(node, 'next')]

    def statement(self, statement: ast.stmt, incoming: Predecessors) -> Predecessors:
        if isinstance(statement, ast.Try):
            return self.try_except(statement, incoming)
        if isinstance(statement, (ast.While, ast.For)):
            return self.loop(statement, incoming)
        if isinstance(statement, (ast.Break, ast.Continue)):
            return self.build_loop_control(statement, incoming)
        if isinstance(statement, ast.If):
            return self.build_if(statement, incoming)
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return)):
            call = self._find_call(statement)
            if call is not None:
                return self.build_call(statement, call, incoming)
        if isinstance(statement, ast.Return):
            return self.build_return(statement, incoming)
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.Pass)):
            current = self.operation('statement', self.text(statement), statement, incoming,
                                     may_raise=not isinstance(statement, ast.Pass))
            return [(current, 'next')]
        if isinstance(statement, (ast.Import, ast.ImportFrom)):
            current = self.operation('statement', self.text(statement), statement, incoming,
                                     may_raise=False)
            return [(current, 'next')]
        if isinstance(statement, ast.FunctionDef):
            return self.build_function_def(statement, incoming)
        if isinstance(statement, ast.Raise):
            return self.build_raise(statement, incoming)
        raise ValueError(f'Unexpected statement after feature validation: {type(statement).__name__}')

    def build_raise(self, statement: ast.Raise, incoming: Predecessors) -> Predecessors:
        current = self.node('raise', self.text(statement), statement)
        self.connect(incoming, current)
        target = self.exception_target or self.exception_end()
        self.edge(current, target, 'exception')
        return []

    def build_if(self, statement: ast.If, incoming: Predecessors) -> Predecessors:
        """Build separate branches and return only their normal outgoing paths."""
        decision = self.operation('condition', self.text(statement.test), statement.test, incoming)

        # Each branch starts at the same decision with a different edge type.
        # An elif is another ast.If in orelse, so recursion preserves the chain.
        true_exits = self.block(statement.body, [(decision, 'true')])
        false_exits = self.block(statement.orelse, [(decision, 'false')])

        # An absent else has no statements: block returns the pending false edge.
        # A return branch contributes no exits. The next statement connects only
        # surviving paths, becoming the merge without a synthetic join node.
        return true_exits + false_exits

    def build_return(self, statement: ast.Return, incoming: Predecessors) -> Predecessors:
        """Connect a terminal return to End and provide no normal successor."""
        # Preserve the existing exception abstraction: evaluating a return value
        # may fail, but the return transfer itself never falls through.
        can_raise = (self.exception_target is not None) or self.in_handler
        if self.track_exceptions and can_raise and statement.value is not None:
            evaluated = self.operation('statement', 'Evaluate return: ' + self.text(statement.value),
                                       statement.value, incoming)
            incoming = [(evaluated, 'next')]
        current = self.node('return', self.text(statement), statement)
        self.connect(incoming, current)
        self.edge(current, self.end, 'return')
        # Empty exits stop subsequent statements on this path. In an if, the
        # other branch may still supply exits and keep the outer block reachable.
        return []

    def build_function_def(self, statement: ast.FunctionDef, incoming: Predecessors) -> Predecessors:
        key = (self.file.file_id, statement.lineno, statement.col_offset, statement.name)
        target_graph_id = self.ids.make('graph', 'function', *key)
        current = self.node('function', f'def {statement.name}(...)', statement)
        self.connect(incoming, current)
        self.graph_references.append(GraphReference(
            source_graph_id=self.graph_id,
            source_node_id=current,
            target_graph_id=target_graph_id))
        return [(current, 'next')]

    def build_loop_control(
        self, statement: ast.Break | ast.Continue, incoming: Predecessors,
    ) -> Predecessors:
        """Terminate this body path at the innermost active loop's exit/header."""
        context = self.loops[-1]  # Feature validation rejects missing loop owners.
        is_break = isinstance(statement, ast.Break)
        current = self.node('break' if is_break else 'continue', self.text(statement), statement)
        self.connect(incoming, current)
        if is_break:
            # The successor is not known yet. Save this exit separately from
            # exhaustion so it can skip this loop's else suite.
            context.breaks.append((current, 'break'))
        else:
            # For loops continue at iterator advancement, never iterator setup.
            # While loops continue at the condition test.
            self.edge(current, context.header, 'continue')
        return []

    def loop(self, statement: ast.While | ast.For, incoming: Predecessors) -> Predecessors:
        """Build repetition, then route exhaustion through else and breaks around it."""
        if isinstance(statement, ast.For):
            setup = self.operation('statement', 'Iterate: ' + self.text(statement.iter), statement.iter, incoming)
            header = self.operation('loop', 'Next: ' + self.text(statement.target), statement.target, [(setup, 'next')])
            constant = None
        else:
            header = self.operation('loop', self.text(statement.test), statement.test, incoming)
            constant = None
            if isinstance(statement.test, ast.Constant) and type(statement.test.value) is bool:
                constant = statement.test.value
        context = _Loop(header)
        self.loops.append(context)
        exits = self.block(statement.body, [] if constant is False else [(header, 'true')])
        # Else is outside this loop's body context. An inner loop's else may
        # control an outer loop, but must never break/continue the finished loop.
        self.loops.pop()
        if exits:
            # Preserve true/false labels on pending branch exits, then use a
            # separate synthetic latch for the actual back edge.
            latch = self.node('statement', 'Loop back')
            self.connect(exits, latch)
            self.edge(latch, header, 'back')
        normal_completion = [] if constant is True else [(header, 'false')]
        else_exits = self.block(statement.orelse, normal_completion)
        # Only false/exhaustion can enter else, including zero body iterations.
        # A return/exception does not appear in either set of normal exits.
        return else_exits + context.breaks

    def try_except(self, statement: ast.Try, incoming: Predecessors) -> Predecessors:
        dispatch = self.node('exceptionDispatch', 'Exception dispatch')
        outer_target = self.exception_target
        self.exception_target = dispatch
        normal = self.block(statement.body, incoming)
        self.exception_target = outer_target

        handler_exits: Predecessors = []
        if statement.handlers:
            if not any(edge.target_id == dispatch for edge in self.edges):
                self.nodes = [node for node in self.nodes if node.node_id != dispatch]
                for handler in statement.handlers:
                    self.diagnostics.append(self.diagnostic(handler, 'UNREACHABLE_HANDLER',
                        'No modeled exceptional path reaches this handler; nodes omitted.', 'warning'))
            else:
                unmatched: Predecessors = [(dispatch, 'exception')]
                for handler in statement.handlers:
                    label = 'except' if handler.type is None else 'except ' + self.text(handler.type)
                    if handler.name:
                        label += f' as {handler.name}'
                    match = self.node('handler', label, handler)
                    self.connect(unmatched, match)
                    if handler.type is None:
                        body_entry: Predecessors = [(match, 'next')]
                        unmatched = []
                    else:
                        body_entry = [(match, 'true')]
                        unmatched = [(match, 'false')]
                        self.edge(match, self.exception_end(), 'exception')
                    was_in_handler = self.in_handler
                    self.in_handler = True
                    try:
                        handler_exits.extend(self.block(handler.body, body_entry))
                    finally:
                        self.in_handler = was_in_handler
                if unmatched:
                    unhandled = self.node('statement', 'Unhandled exception')
                    self.connect(unmatched, unhandled)
                    self.edge(unhandled, self.exception_end(), 'unhandled')
        else:
            if not any(edge.target_id == dispatch for edge in self.edges):
                self.nodes = [node for node in self.nodes if node.node_id != dispatch]
            else:
                self.edge(dispatch, outer_target or self.exception_end(), 'exception')

        if statement.orelse and normal:
            normal = self.block(statement.orelse, normal)

        surviving = normal + handler_exits
        if statement.finalbody and surviving:
            surviving = self.block(statement.finalbody, surviving)
        return surviving


class _ModuleBuilder(_FunctionBuilder):
    def __init__(self, tree: ast.Module, file: FileInput, ids: RevisionIds,
                 local_functions: dict[str, ast.FunctionDef] | None = None,
                 functions_by_id: dict[str, FunctionInfo] | None = None,
                 call_references: list[CallReference] | None = None) -> None:
        self.tree = tree
        self.file = file
        self.ids = ids
        self.local_functions = local_functions or {}
        self.functions_by_id = functions_by_id or {}
        self.call_references = call_references or []
        self.calls_by_loc = {
            (c.location.start_line, c.location.start_column): c
            for c in self.call_references if c.file_id == file.file_id
        }
        self.graph_id = ids.make('graph', 'module', file.file_id)
        self.graph_type = 'module'
        self.nodes: list[FlowNode] = []
        self.edges: list[FlowEdge] = []
        self.mappings: list[SourceMapping] = []
        self.diagnostics: list[Diagnostic] = []
        self.graph_references: list[GraphReference] = []
        self.loops: list[_Loop] = []
        self.node_count = 0
        self.exception_target: str | None = None
        self.exceptional_end: str | None = None
        self.in_handler = False
        self.track_exceptions = any(isinstance(node, (ast.Try, ast.Raise)) for node in ast.walk(tree))

    def graph(self, status: str, empty: bool = False) -> GraphModel:
        return GraphModel(graph_id=self.graph_id, graph_type='module', status=status,
                          file_id=self.file.file_id, function_id=None,
                          nodes=[] if empty else self.nodes, edges=[] if empty else self.edges)

    def build(self) -> CFGResult:
        start = self.node('start', 'Start')
        self.end = self.node('end', 'End')
        remaining = self.block(self.tree.body, [(start, 'next')])
        self.connect(remaining, self.end)
        if not any(edge.target_id == self.end for edge in self.edges):
            self.nodes = [n for n in self.nodes if n.node_id != self.end]
            self.mappings = [m for m in self.mappings if m.node_id != self.end]
        return CFGResult(self.graph('complete'), self.mappings, self.diagnostics, self.graph_references)


class _FileFlowBuilder(_FunctionBuilder):
    """Build complete file-level execution CFG with local function inlining and cross-file call links."""

    def __init__(
        self,
        tree: ast.Module,
        file: FileInput,
        ids: RevisionIds,
        local_functions: dict[str, ast.FunctionDef],
        functions_by_id: dict[str, FunctionInfo],
        call_references: list[CallReference],
    ) -> None:
        self.tree = tree
        self.file = file
        self.ids = ids
        self.graph_id = ids.make('graph', 'file', file.file_id)
        self.graph_type = 'file'
        self.local_functions = local_functions
        self.functions_by_id = functions_by_id
        self.call_references = call_references
        self.calls_by_loc = {
            (c.location.start_line, c.location.start_column): c
            for c in call_references if c.file_id == file.file_id
        }
        self.nodes: list[FlowNode] = []
        self.edges: list[FlowEdge] = []
        self.mappings: list[SourceMapping] = []
        self.diagnostics: list[Diagnostic] = []
        self.graph_references: list[GraphReference] = []
        self.loops: list[_Loop] = []
        self.node_count = 0
        self.exception_target: str | None = None
        self.exceptional_end: str | None = None
        self.in_handler = False
        self.track_exceptions = any(isinstance(node, (ast.Try, ast.Raise)) for node in ast.walk(tree))
        self.active_call_stack: set[str] = set()
        self.current_inlined_returns: list[tuple[str, EdgeType]] | None = None

    def graph(self, status: str, empty: bool = False) -> GraphModel:
        return GraphModel(
            graph_id=self.graph_id,
            graph_type='file',
            status=status,
            file_id=self.file.file_id,
            function_id=None,
            nodes=[] if empty else self.nodes,
            edges=[] if empty else self.edges,
        )

    def build(self) -> CFGResult:
        start = self.node('start', 'Start')
        self.end = self.node('end', 'End')
        remaining = self.block(self.tree.body, [(start, 'next')])
        self.connect(remaining, self.end)
        if not any(edge.target_id == self.end for edge in self.edges):
            self.nodes = [n for n in self.nodes if n.node_id != self.end]
            self.mappings = [m for m in self.mappings if m.node_id != self.end]
        return CFGResult(self.graph('complete'), self.mappings, self.diagnostics, self.graph_references)

    def statement(self, statement: ast.stmt, incoming: Predecessors) -> Predecessors:
        if isinstance(statement, ast.FunctionDef):
            return self.build_function_def(statement, incoming)
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.Expr, ast.Return)):
            call = self._find_call(statement)
            if call is not None:
                return self.build_call(statement, call, incoming)
        return super().statement(statement, incoming)

    def _find_call(self, statement: ast.stmt) -> ast.Call | None:
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            return statement.value
        if isinstance(statement, (ast.Assign, ast.AnnAssign)) and isinstance(statement.value, ast.Call):
            return statement.value
        if isinstance(statement, ast.Return) and isinstance(statement.value, ast.Call):
            return statement.value
        calls = [n for n in ast.walk(statement) if isinstance(n, ast.Call)]
        if len(calls) == 1:
            return calls[0]
        return None

    def build_function_def(self, statement: ast.FunctionDef, incoming: Predecessors) -> Predecessors:
        key = (self.file.file_id, statement.lineno, statement.col_offset, statement.name)
        target_graph_id = self.ids.make('graph', 'function', *key)
        current = self.node('function', statement.name, statement)
        self.connect(incoming, current)
        self.graph_references.append(GraphReference(
            source_graph_id=self.graph_id,
            source_node_id=current,
            target_graph_id=target_graph_id))
        return [(current, 'next')]

    def build_call(self, statement: ast.stmt, call: ast.Call, incoming: Predecessors) -> Predecessors:
        target_fn = self._resolve_target(call)
        is_ret = isinstance(statement, ast.Return)
        is_assign = isinstance(statement, (ast.Assign, ast.AnnAssign))

        # Evaluate any nested calls in arguments first
        for arg in call.args:
            for nested in self._top_nested_calls(arg):
                if nested is not call:
                    nested_fn = self._resolve_target(nested)
                    if nested_fn:
                        nested_stmt = ast.Expr(value=nested)
                        incoming = self.build_call(nested_stmt, nested, incoming)

        # Same-file function call -> Inline expansion with recursion guard
        if target_fn and target_fn.file_id == self.file.file_id and target_fn.function_name in self.local_functions:
            if target_fn.function_id in self.active_call_stack:
                # Prevent infinite expansion on recursive calls
                node_type = 'return' if is_ret else 'statement'
                node = self.node(node_type, f'{self.text(statement)} (recursive)', statement)
                self.connect(incoming, node)
                if is_ret:
                    if self.current_inlined_returns is not None:
                        self.current_inlined_returns.append((node, 'next'))
                    else:
                        self.edge(node, self.end, 'return')
                    return []
                return [(node, 'next')]

            self.active_call_stack.add(target_fn.function_id)
            saved_returns = self.current_inlined_returns
            self.current_inlined_returns = []

            # Emit Call Entry Node
            call_node = self.node('function', f'Call {self.text(call)}', call)
            self.connect(incoming, call_node)
            self.graph_references.append(GraphReference(
                source_graph_id=self.graph_id,
                source_node_id=call_node,
                target_graph_id=target_fn.graph_id,
            ))

            func_def = self.local_functions[target_fn.function_name]
            body_exits = self.block(func_def.body, [(call_node, 'next')])
            raw_exits = body_exits + self.current_inlined_returns

            self.current_inlined_returns = saved_returns
            self.active_call_stack.remove(target_fn.function_id)

            if is_assign and raw_exits:
                assign_node = self.node('statement', self.text(statement), statement)
                self.connect(raw_exits, assign_node)
                return [(assign_node, 'next')]

            if is_ret and raw_exits:
                if self.current_inlined_returns is not None:
                    return raw_exits
                for src_id, edge_type in raw_exits:
                    self.edge(src_id, self.end, 'return')
                return []

            return raw_exits

        # Cross-file imported call -> Clickable function-call node
        if target_fn and target_fn.file_id != self.file.file_id:
            node = self.node('function', self.text(statement), statement)
            self.connect(incoming, node)
            self.graph_references.append(GraphReference(
                source_graph_id=self.graph_id,
                source_node_id=node,
                target_graph_id=target_fn.graph_id,
            ))
            if is_ret:
                if self.current_inlined_returns is not None:
                    self.current_inlined_returns.append((node, 'next'))
                else:
                    self.edge(node, self.end, 'return')
                return []
            return [(node, 'next')]

        # Builtin, external or unresolved call
        node_type = 'return' if is_ret else 'statement'
        node = self.operation(node_type, self.text(statement), statement, incoming,
                              may_raise=not isinstance(statement, ast.Pass))
        if is_ret:
            if self.current_inlined_returns is not None:
                self.current_inlined_returns.append((node, 'next'))
            else:
                self.edge(node, self.end, 'return')
            return []
        return [(node, 'next')]

    def build_return(self, statement: ast.Return, incoming: Predecessors) -> Predecessors:
        can_raise = (self.exception_target is not None) or self.in_handler
        if self.track_exceptions and can_raise and statement.value is not None:
            evaluated = self.operation('statement', 'Evaluate return: ' + self.text(statement.value),
                                       statement.value, incoming)
            incoming = [(evaluated, 'next')]
        current = self.node('return', self.text(statement), statement)
        self.connect(incoming, current)
        if self.current_inlined_returns is not None:
            self.current_inlined_returns.append((current, 'next'))
            return []
        self.edge(current, self.end, 'return')
        return []
