"""Extract conservative lexical metadata without CFGs or execution."""
import ast
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .RevisionIds import RevisionIds
from .models import Diagnostic, FileInput, FunctionInfo, JsonModel, ParameterInfo, SourceLocation, SymbolInfo
from .PythonParser import ast_location
from .SymbolTable import ScopeInfo, SymbolTable
from .FeatureValidator import FeatureValidator
from .ImportRelationship import ImportRelationship


@dataclass(kw_only=True)
class CallSite(JsonModel):
    """Unresolved syntactic call occurrence, with its actual enclosing scope."""
    call_id: str
    file_id: str
    scope_id: str
    caller_function_id: str | None
    location: SourceLocation
    expression: str
    callee_expression: str
    direct_name: str | None


@dataclass
class ASTAnalysis:
    """File-local intermediate metadata; graph IDs are reserved, not built graphs."""
    file_id: str
    module_scope_id: str
    symbol_table: SymbolTable
    functions: list[FunctionInfo] = field(default_factory=list)
    call_sites: list[CallSite] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    imports: list[ImportRelationship] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize a development snapshot without ASTs or fabricated graphs."""
        return {'fileId': self.file_id, 'moduleScopeId': self.module_scope_id,
                'functions': [item.to_dict() for item in self.functions],
                'symbolTable': self.symbol_table.to_dict(),
                'callSites': [item.to_dict() for item in self.call_sites],
                'diagnostics': [item.to_dict() for item in self.diagnostics]}


class ASTAnalyzer:
    """Extract a fresh file-local analysis using explicit project/revision identity."""

    def analyze(self, tree: ast.Module, file_input: FileInput, ids: RevisionIds) -> ASTAnalysis:
        """Inspect the AST paired with its exact source snapshot; never reparse/run it."""
        if not isinstance(tree, ast.Module):
            raise TypeError('ASTAnalyzer requires a successfully parsed ast.Module')
        file_input.__post_init__()
        return _FileAnalyzer(file_input, ids).analyze(tree)


class _FileAnalyzer:
    """Request-local worker; no analysis state lives on the public analyzer."""

    def __init__(self, file: FileInput, ids: RevisionIds) -> None:
        self.file = file
        self.ids = ids
        # Display-only module name. It is not an import-resolution claim.
        path = PurePosixPath(file.file_path.replace('\\', '/'))
        # Paths are user metadata, not guaranteed filesystem filenames. Root-only
        # paths have no suffix-bearing name; still allow same-file analysis.
        self.module_name = '.'.join(path.with_suffix('').parts) if path.name else file.file_name
        module_scope = ids.make('scope', 'module', file.file_id)
        self.result = ASTAnalysis(file.file_id, module_scope, SymbolTable())
        self.table = self.result.symbol_table
        self.table.add_scope(ScopeInfo(scope_id=module_scope, name=self.module_name,
                                     kind='module', file_id=file.file_id))

    def analyze(self, tree: ast.Module) -> ASTAnalysis:
        self.result.diagnostics.extend(FeatureValidator().validate(tree, self.file.file_id).diagnostics)
        for statement in tree.body:
            if isinstance(statement, ast.FunctionDef):
                self._function(statement)
            else:
                self._walk([statement], self.result.module_scope_id)
        self.result.call_sites.sort(key=lambda call: (call.location.start_line, call.location.start_column,
                                                      call.location.end_line, call.location.end_column))
        return self.result

    def _text(self, node: ast.AST | None) -> str | None:
        return ast.get_source_segment(self.file.file_content, node) if node is not None else None

    def _bind(self, node: ast.AST, scope_id: str, name: str, kind: str,
              function_id: str | None = None, import_target: str | None = None) -> None:
        self.table.bind(SymbolInfo(scope_id=scope_id, name=name, kind=kind, file_id=self.file.file_id,
                                   location=ast_location(node, self.file.file_id), function_id=function_id,
                                   import_target=import_target))

    def _incomplete(self, node: ast.AST, scope_id: str, message: str) -> None:
        self.table.mark_incomplete(scope_id)
        self.result.diagnostics.append(Diagnostic(
            severity='warning', code='INCOMPLETE_SCOPE', file_id=self.file.file_id,
            source_location=ast_location(node, self.file.file_id),
            message=f'{self.table.scope(scope_id).name}: {message}'))

    def _parameters(self, args: ast.arguments) -> list[tuple[ast.arg, ParameterInfo]]:
        """Pair signature nodes with metadata, aligning trailing positional defaults."""
        positional = args.posonlyargs + args.args
        default_start = len(positional) - len(args.defaults)
        parameters = []
        for index, arg in enumerate(positional):
            kind = 'positionalOnly' if index < len(args.posonlyargs) else 'positionalOrKeyword'
            parameters.append((arg, ParameterInfo(name=arg.arg, kind=kind,
                               has_default=index >= default_start, annotation=self._text(arg.annotation))))
        if args.vararg is not None:
            parameters.append((args.vararg, ParameterInfo(name=args.vararg.arg, kind='varPositional',
                               has_default=False, annotation=self._text(args.vararg.annotation))))
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            parameters.append((arg, ParameterInfo(name=arg.arg, kind='keywordOnly',
                               has_default=default is not None, annotation=self._text(arg.annotation))))
        if args.kwarg is not None:
            parameters.append((args.kwarg, ParameterInfo(name=args.kwarg.arg, kind='varKeyword',
                               has_default=False, annotation=self._text(args.kwarg.annotation))))
        return parameters

    def _function(self, node: ast.FunctionDef) -> None:
        """Register a direct function, then inspect its header and body in their scopes."""
        key = (self.file.file_id, node.lineno, node.col_offset, node.name)
        function_id = self.ids.make('function', *key)
        scope_id = self.ids.make('scope', 'function', *key)
        location = ast_location(node, self.file.file_id)
        parameters = self._parameters(node.args)
        qualified_name = f'{self.module_name}.{node.name}'
        self.result.functions.append(FunctionInfo(
            function_id=function_id, function_name=node.name, qualified_name=qualified_name,
            file_id=self.file.file_id, parameters=[info for _, info in parameters],
            start_line=location.start_line, end_line=location.end_line,
            start_column=location.start_column, end_column=location.end_column,
            graph_id=self.ids.make('graph', 'function', *key), scope_id=scope_id))
        self._bind(node, self.result.module_scope_id, node.name, 'function', function_id)
        self.table.add_scope(ScopeInfo(scope_id=scope_id, name=qualified_name, kind='function',
                                     file_id=self.file.file_id, parent_scope_id=self.result.module_scope_id,
                                     function_id=function_id))
        for arg, _ in parameters:
            self._bind(arg, scope_id, arg.arg, 'parameter')
        # Defaults/decorator expressions belong to the defining scope, not the
        # function body. Annotation text is retained but its evaluation is deferred.
        self._walk([*node.decorator_list, *node.args.defaults,
                    *(value for value in node.args.kw_defaults if value is not None)],
                   self.result.module_scope_id)
        if node.decorator_list or node.type_params:
            self._incomplete(node, scope_id, 'decorated/generic function semantics are not resolved')
            self.table.mark_incomplete(self.result.module_scope_id)
        if self._has_scope_directive(node.body):
            self._incomplete(node, scope_id, 'global/nonlocal changes binding ownership; body omitted')
            return
        self._walk(node.body, scope_id)

    @staticmethod
    def _has_scope_directive(body: list[ast.stmt]) -> bool:
        pending = list(body)
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                return True
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            pending.extend(ast.iter_child_nodes(node))
        return False

    def _walk(self, nodes: list[ast.AST], scope_id: str) -> None:
        """Collect bindings/calls in one scope without descending into inner scopes.

        This is lexical discovery, not execution simulation: even a zero-iteration
        loop can make a target local throughout a function. Unsupported scope
        behavior is diagnosed rather than guessed.
        """
        pending = list(reversed(nodes))
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = 'function' if not isinstance(node, ast.ClassDef) else self._binding_kind(scope_id)
                self._bind(node, scope_id, node.name, kind)
                self._incomplete(node, scope_id, 'nested/conditional/async/class declaration body omitted')
                continue
            if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                self._incomplete(node, scope_id, 'inner expression scope omitted')
                continue
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                self._imports(node, scope_id)
                continue
            if isinstance(node, (ast.For, ast.While)):
                # Loops do not create Python scopes. Inspect their targets/tests
                # and bodies in the current scope, but keep loop-else conservative.
                # Inspect header, body and else in current scope


                pending.extend(reversed(list(ast.iter_child_nodes(node))))
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                self._bind(node, scope_id, node.id, self._binding_kind(scope_id))
            if isinstance(node, ast.Call):
                location = ast_location(node, self.file.file_id)
                self.result.call_sites.append(CallSite(
                    call_id=self.ids.make('call', self.file.file_id, node.lineno, node.col_offset,
                                         node.end_lineno, node.end_col_offset),
                    file_id=self.file.file_id, scope_id=scope_id,
                    caller_function_id=self.table.scope(scope_id).function_id, location=location,
                    expression=self._text(node), callee_expression=self._text(node.func),
                    direct_name=node.func.id if isinstance(node.func, ast.Name) else None))
            if isinstance(node, ast.Try):
                if node.orelse or node.finalbody:
                    self._incomplete(node, scope_id, 'try else/finally subtrees omitted from binding analysis')
                for handler in reversed(node.handlers):
                    pending.append(handler)
                for child in reversed(node.body):
                    pending.append(child)
                continue
            if isinstance(node, ast.ExceptHandler):
                if node.name is not None:
                    self._incomplete(node, scope_id, 'exception alias binding and cleanup are not modeled')
                for child in reversed(node.body):
                    pending.append(child)
                if node.type is not None:
                    pending.append(node.type)
                continue
            if isinstance(node, ast.stmt) and not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign,
                                                                 ast.Expr, ast.If, ast.Return, ast.Pass,
                                                                 ast.Break, ast.Continue)):
                self._incomplete(node, scope_id, f'{type(node).__name__} subtree omitted from binding analysis')
                continue
            if isinstance(node, (ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr)):
                self._incomplete(node, scope_id, f'{type(node).__name__} expression omitted')
                continue
            if isinstance(node, ast.AnnAssign):
                # An annotation binds a local name even without a runtime value.
                children = [node.target, node.annotation] + ([node.value] if node.value is not None else [])
            else:
                children = list(ast.iter_child_nodes(node))
            pending.extend(reversed(children))

    def _binding_kind(self, scope_id: str) -> str:
        return 'module' if self.table.scope(scope_id).kind == 'module' else 'local'

    def _imports(self, node: ast.Import | ast.ImportFrom, scope_id: str) -> None:
        for alias in node.names:
            if alias.name == '*':
                self._incomplete(node, scope_id, 'star import introduces unknown names')
                continue
            if isinstance(node, ast.Import):
                name = alias.asname or alias.name.split('.')[0]
                target = alias.name if alias.asname else alias.name.split('.')[0]
            else:
                name = alias.asname or alias.name
                module = '.' * node.level + (node.module or '')
                target = module + ('' if module.endswith('.') else '.') + alias.name
            self._bind(alias, scope_id, name, 'import', import_target=target)
            self.result.imports.append(ImportRelationship(
                self.file.file_id, scope_id, name,
                alias.name if isinstance(node, ast.Import) else (node.module or ''),
                None if isinstance(node, ast.Import) else alias.name,
                0 if isinstance(node, ast.Import) else node.level,
                ast_location(alias, self.file.file_id), node.col_offset == 0))
