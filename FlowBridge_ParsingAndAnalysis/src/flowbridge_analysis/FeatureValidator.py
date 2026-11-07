"""Inspect parsed AST feature support without executing source."""
import ast
from dataclasses import dataclass, field
from .models import Diagnostic
from .PythonParser import ast_location


@dataclass
class FeatureValidationResult:
    """Feature support only: syntax must already have been parsed successfully."""
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        """Whether the entire inspected file fits the currently supported subset."""
        return not any(item.severity == 'error' for item in self.diagnostics)


@dataclass(frozen=True)
class _Visit:
    """One pending AST node and its lexical control-flow validation context."""
    node: ast.AST
    scope: str
    at_module: bool = False
    is_first: bool = False
    loop_depth: int = 0
    try_depth: int = 0


class FeatureValidator:
    """Inspect explicit AST allowlists; never execute or resolve source expressions."""

    def validate(self, tree: 'ast.Module', file_id: str) -> FeatureValidationResult:
        """Inspect all supported branches, including statements after a return.

        Direct module functions, absolute imports and a leading docstring are accepted
        at module level. Unsupported subtrees get one diagnostic at their root;
        other branches/functions continue to be inspected.
        """
        if not isinstance(tree, ast.Module):
            raise TypeError('FeatureValidator requires a successfully parsed ast.Module')
        if not isinstance(file_id, str) or not file_id.strip():
            raise ValueError('file_id must be a nonblank string')
        result = FeatureValidationResult()

        def reject(node: ast.AST, scope: str, reason: str) -> None:
            result.diagnostics.append(Diagnostic(
                severity='error', code='UNSUPPORTED_FEATURE', file_id=file_id,
                source_location=ast_location(node, file_id),
                message=f'{scope}: {type(node).__name__} is unsupported: {reason}'))

        # Work items carry their enclosing scope; a local stack avoids shared
        # visitor state and Python recursion on deeply nested expressions.
        pending = [_Visit(node, '<module>', at_module=True, is_first=index == 0)
                   for index, node in reversed(list(enumerate(tree.body)))]
        while pending:
            visit = pending.pop()
            node = visit.node
            scope = visit.scope
            at_module = visit.at_module
            is_first = visit.is_first
            loop_depth = visit.loop_depth
            try_depth = visit.try_depth
            if isinstance(node, ast.Return) and scope == '<module>':
                reject(node, scope, 'return statement outside function')
                continue
            if isinstance(node, ast.FunctionDef):
                if not at_module:
                    reject(node, scope, 'only direct module-level functions are supported')
                    continue
                scope = f'function {node.name} (line {node.lineno})'
                parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                if node.args.vararg is not None:
                    parameters.append(node.args.vararg)
                if node.args.kwarg is not None:
                    parameters.append(node.args.kwarg)
                names: set[str] = set()
                for parameter in parameters:
                    # ast.parse does not perform this compiler-context check.
                    # Reject it before a valid-looking executable CFG is emitted.
                    if parameter.arg in names:
                        reject(parameter, scope, 'duplicate parameter name')
                    names.add(parameter.arg)
                loop_depth = 0
                try_depth = 0
                for decorator in node.decorator_list:
                    reject(decorator, scope, 'decorated functions are not supported')
                for parameter in node.type_params:
                    reject(parameter, scope, 'generic type parameters are not supported')
                children = [node.args, *node.body]
                if node.returns is not None:
                    children.append(node.returns)
            elif at_module:
                # Imports declare bindings for static call resolution. File views
                # are structural: accepting this metadata does not execute imports
                # or claim to model module initialization/control flow.
                if isinstance(node, ast.Import):
                    continue
                if isinstance(node, ast.ImportFrom):
                    if node.module == '__future__':
                        reject(node, scope, 'future directives change language semantics and are not modeled')
                    elif node.level or any(alias.name == '*' for alias in node.names):
                        reject(node, scope, 'relative and star imports are outside static import resolution')
                    continue
                if (is_first and isinstance(node, ast.Expr)
                        and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
                    continue
                if isinstance(node, (ast.Break, ast.Continue)):
                    reject(node, scope, 'break/continue requires an enclosing loop')
                    continue
                if isinstance(node, (ast.For, ast.While)):
                    for child in reversed(node.orelse):
                        pending.append(_Visit(child, scope, loop_depth=loop_depth, try_depth=try_depth))
                    for child in reversed(node.body):
                        pending.append(_Visit(child, scope, loop_depth=loop_depth + 1, try_depth=try_depth))
                    header_nodes = [node.target, node.iter] if isinstance(node, ast.For) else [node.test]
                    for child in reversed(header_nodes):
                        pending.append(_Visit(child, scope, loop_depth=loop_depth, try_depth=try_depth))
                    continue
                if isinstance(node, ast.Try):
                    if try_depth or node.orelse or node.finalbody or not node.handlers:
                        reject(node, scope, 'only non-nested try/except without else/finally is modeled')
                        continue
                    try_depth += 1
                    children = list(ast.iter_child_nodes(node))
                    for index, handler in enumerate(node.handlers):
                        if handler.type is None and index != len(node.handlers) - 1:
                            reject(handler, scope, 'bare except must be last')
                    result.diagnostics.append(Diagnostic(
                        severity='warning', code='CONSERVATIVE_EXCEPTIONS', file_id=file_id,
                        source_location=ast_location(node, file_id),
                        message=f'{scope}: exception types are not inferred; ordered handler matches are possible alternatives.'))
                    for child in reversed(children):
                        pending.append(_Visit(child, scope, loop_depth=loop_depth, try_depth=try_depth))
                    continue
                if type(node) not in _SUPPORTED_AST_TYPES:
                    reject(node, scope, 'outside the documented statement/expression subset')
                    continue
                children = list(ast.iter_child_nodes(node))
                for child in reversed(children):
                    pending.append(_Visit(child, scope, loop_depth=loop_depth, try_depth=try_depth))
                continue
            elif isinstance(node, (ast.For, ast.While)):
                # The else suite runs after this loop has finished. Validate it
                # using only enclosing loop depth, so its controls target an outer
                # body (or are rejected when no outer loop exists).
                for child in reversed(node.orelse):
                    pending.append(_Visit(child, scope, loop_depth=loop_depth, try_depth=try_depth))
                for child in reversed(node.body):
                    pending.append(_Visit(child, scope, loop_depth=loop_depth + 1, try_depth=try_depth))
                header_nodes = [node.target, node.iter] if isinstance(node, ast.For) else [node.test]
                for child in reversed(header_nodes):
                    pending.append(_Visit(child, scope, loop_depth=loop_depth, try_depth=try_depth))
                continue
            elif isinstance(node, (ast.Break, ast.Continue)):
                if not loop_depth:
                    reject(node, scope, 'break/continue requires an enclosing loop')
                children = []
            elif isinstance(node, ast.Try):
                if try_depth or node.orelse or node.finalbody or not node.handlers:
                    reject(node, scope, 'only non-nested try/except without else/finally is modeled')
                    continue
                try_depth += 1
                children = list(ast.iter_child_nodes(node))
                for index, handler in enumerate(node.handlers):
                    if handler.type is None and index != len(node.handlers) - 1:
                        reject(handler, scope, 'bare except must be last')
                result.diagnostics.append(Diagnostic(
                    severity='warning', code='CONSERVATIVE_EXCEPTIONS', file_id=file_id,
                    source_location=ast_location(node, file_id),
                    message=f'{scope}: exception types are not inferred; ordered handler matches are possible alternatives.'))
            elif isinstance(node, ast.ExceptHandler):
                if node.name is not None:
                    reject(node, scope, 'exception aliases require cleanup semantics not yet modeled')
                    continue
                simple_type = node.type is None or isinstance(node.type, ast.Name) or (
                    isinstance(node.type, ast.Tuple) and all(isinstance(item, ast.Name) for item in node.type.elts))
                if not simple_type:
                    reject(node, scope, 'handler types must be names or tuples of names')
                    continue
                children = list(ast.iter_child_nodes(node))
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in ('eval', 'exec', 'compile'):
                    reject(node, scope, f'dynamic execution through {node.func.id}() is unsupported')
                    continue
                children = list(ast.iter_child_nodes(node))
            elif type(node) not in _SUPPORTED_AST_TYPES:
                reject(node, scope, 'outside the documented statement/expression subset')
                continue
            else:
                children = list(ast.iter_child_nodes(node))
            # Reverse insertion keeps the stack's visits in source order. Each
            # sibling gets its own context; loop depth cannot leak past a loop.
            for child in reversed(children):
                pending.append(_Visit(child, scope, loop_depth=loop_depth, try_depth=try_depth))
        return result


# Expressions are atomic for statement CFGs, but their children are still
# inspected so a comprehension, lambda, yield or await cannot hide inside a call.
_SUPPORTED_AST_TYPES = frozenset({
    ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.If, ast.Return, ast.Pass,
    ast.Name, ast.Constant, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare,
    ast.Call, ast.Attribute, ast.Subscript, ast.Slice, ast.List, ast.Tuple,
    ast.Set, ast.Dict, ast.Starred, ast.IfExp, ast.JoinedStr, ast.FormattedValue,
    ast.arguments, ast.arg, ast.keyword, ast.Load, ast.Store,
    ast.Add, ast.Sub, ast.Mult, ast.MatMult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd,
    ast.Invert, ast.Not, ast.UAdd, ast.USub, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
})
