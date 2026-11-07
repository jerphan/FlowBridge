"""Statement-level CFG construction from pending normal predecessors."""
import ast
from dataclasses import dataclass, field, replace

from .RevisionIds import RevisionIds
from .models import Diagnostic, EdgeType, FileInput, FlowEdge, FlowNode, GraphModel, GraphReference, NodeType, SourceMapping
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

    def build(self, function: ast.FunctionDef, file_input: FileInput, ids: RevisionIds) -> CFGResult:
        """Validate the entire function before constructing executable paths."""
        if not isinstance(function, ast.FunctionDef):
            raise TypeError('CFGBuilder requires an ast.FunctionDef')
        file_input.__post_init__()
        worker = _FunctionBuilder(function, file_input, ids)
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

    def build_module(self, tree: ast.Module, file_input: FileInput, ids: RevisionIds) -> CFGResult:
        """Build a fresh execution CFG for top-level module statements."""
        if not isinstance(tree, ast.Module):
            raise TypeError('CFGBuilder.build_module requires an ast.Module')
        file_input.__post_init__()
        worker = _ModuleBuilder(tree, file_input, ids)
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


class _FunctionBuilder:
    def __init__(self, function: ast.FunctionDef, file: FileInput, ids: RevisionIds) -> None:
        self.function = function
        self.file = file
        self.ids = ids
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
        self.track_exceptions = any(isinstance(node, ast.Try) for node in ast.walk(function))

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

    def statement(self, statement: ast.stmt, incoming: Predecessors) -> Predecessors:
        if isinstance(statement, ast.Try):
            return self.try_except(statement, incoming)
        if isinstance(statement, (ast.While, ast.For)):
            return self.loop(statement, incoming)
        if isinstance(statement, (ast.Break, ast.Continue)):
            return self.build_loop_control(statement, incoming)
        if isinstance(statement, ast.If):
            return self.build_if(statement, incoming)
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
        raise ValueError(f'Unexpected statement after feature validation: {type(statement).__name__}')

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
        # If no protected operation can raise in our abstraction (e.g. try: pass),
        # there is no executable entry into any handler. Do not invent one.
        if not any(edge.target_id == dispatch for edge in self.edges):
            self.nodes = [node for node in self.nodes if node.node_id != dispatch]
            for handler in statement.handlers:
                self.diagnostics.append(self.diagnostic(handler, 'UNREACHABLE_HANDLER',
                    'No modeled exceptional path reaches this handler; nodes omitted.', 'warning'))
            return normal
        unmatched: Predecessors = [(dispatch, 'exception')]
        handler_exits: Predecessors = []
        for handler in statement.handlers:
            label = 'except' if handler.type is None else 'except ' + self.text(handler.type)
            match = self.node('handler', label, handler)
            self.connect(unmatched, match)
            if handler.type is None:
                body_entry: Predecessors = [(match, 'next')]
                unmatched = []
            else:
                body_entry = [(match, 'true')]
                unmatched = [(match, 'false')]
                # Looking up/validating the exception class may itself fail.
                self.edge(match, self.exception_end(), 'exception')
            # Handler operations use the enclosing exception context, never the
            # same try's dispatch. A handler failure cannot enter a sibling handler.
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
        return normal + handler_exits


class _ModuleBuilder(_FunctionBuilder):
    def __init__(self, tree: ast.Module, file: FileInput, ids: RevisionIds) -> None:
        self.tree = tree
        self.file = file
        self.ids = ids
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
        self.track_exceptions = any(isinstance(node, ast.Try) for node in ast.walk(tree))

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
