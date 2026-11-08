"""Bounded lexical call resolution without importing or executing source."""
import builtins
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .ASTAnalyzer import ASTAnalysis, CallSite
from .ImportRelationship import ImportRelationship
from .models import CallReference, FileInput, FunctionInfo

# The UML relationship role uses the existing canonical wire record.
CallRelationship = CallReference


@dataclass
class CallResolution:
    """Intermediate relationships; graph targets are reserved until assembly."""
    call_references: list[CallReference] = field(default_factory=list)
    import_relationships: list[ImportRelationship] = field(default_factory=list)


class CallResolver:
    """Resolve a complete snapshot using lexical bindings and explicit imports."""

    def resolve(self, files: list[FileInput], analyses: list[ASTAnalysis]) -> CallResolution:
        """Accept matching parsed metadata; missing/failed modules stay unresolved.

        Only root-relative .py module paths are indexed. No filesystem lookup,
        runtime module loading, assignment propagation or re-export chasing occurs.
        """
        by_file = {item.file_id: item for item in analyses}
        if len(by_file) != len(analyses) or len({f.file_id for f in files}) != len(files):
            raise ValueError('Duplicate file identity')
        if not set(by_file).issubset({f.file_id for f in files}):
            raise ValueError('Analysis has no matching source file')
        modules: dict[str, list[ASTAnalysis | None]] = {}
        file_packages: dict[str, list[str]] = {}
        for file in files:
            path = PurePosixPath(file.file_path.replace('\\', '/'))
            if not path.name or path.suffix != '.py':
                continue
            parts = list(path.with_suffix('').parts)
            if path.suffix != '.py' or not parts or not all(p.isidentifier() for p in parts):
                continue
            if path.name == '__init__.py':
                file_packages[file.file_id] = list(parts[:-1]) if parts[-1] == '__init__' else list(parts)
            else:
                file_packages[file.file_id] = list(parts[:-1])
            if parts[-1] == '__init__':
                parts.pop()
            if parts:
                modules.setdefault('.'.join(parts), []).append(by_file.get(file.file_id))
        functions = {f.function_id: f for a in analyses for f in a.functions}
        result = CallResolution()
        for analysis in analyses:
            result.import_relationships.extend(analysis.imports)
            for call in analysis.call_sites:
                status, reason, target = self._resolve_call(call, analysis, modules, functions, file_packages)
                result.call_references.append(CallReference(
                    call_id=call.call_id, file_id=call.file_id,
                    caller_function_id=call.caller_function_id, location=call.location,
                    expression=call.expression, resolution=status, reason=reason,
                    target_function_id=target.function_id if target else None,
                    target_graph_id=target.graph_id if target else None))
        return result

    def _resolve_call(self, call: CallSite, analysis: ASTAnalysis,
                      modules: dict[str, list[ASTAnalysis | None]],
                      functions: dict[str, FunctionInfo],
                      file_packages: dict[str, list[str]] | None = None) -> tuple[str, str, FunctionInfo | None]:
        # Only dotted identifiers are candidates. Subscripts, factories and other
        # computed callees cannot be resolved by lexical name lookup.
        parts = call.callee_expression.split('.')
        if not all(part.isidentifier() for part in parts):
            return 'unresolved', 'Dynamic callee expression', None

        lookup = analysis.symbol_table.lookup(call.scope_id, parts[0])
        if not lookup.is_complete:
            return 'unresolved', 'Incomplete lexical scope', None
        if not lookup.bindings:
            if len(parts) == 1 and callable(getattr(builtins, parts[0], None)):
                return 'builtin', 'Unshadowed standard Python builtin', None
            return 'unresolved', 'No lexical binding', None
        if len(lookup.bindings) > 1:
            return 'ambiguous', 'Multiple binding occurrences; execution order not inferred', None
        binding = lookup.bindings[0]
        if binding.kind == 'function' and len(parts) == 1:
            target = functions.get(binding.function_id)
            if target:
                return 'resolved', 'Unique lexical function declaration', target
        if binding.kind != 'import':
            return 'unresolved', 'Binding is not a statically known callable', None
        imports = [item for item in analysis.imports
                   if item.scope_id == binding.scope_id and item.binding_name == binding.name]
        if len(imports) != 1:
            return 'unresolved', 'Import metadata is missing or nonunique', None
        imported = imports[0]
        if not imported.is_module_level:
            return 'unresolved', 'Conditional and function-local imports are unsupported', None

        # Resolve effective module for relative or absolute imports
        is_relative = imported.level > 0
        if is_relative:
            packages = file_packages or {}
            pkg = packages.get(analysis.file_id, [])
            base = list(pkg)
            steps = imported.level - 1
            while steps > 0 and base:
                base.pop()
                steps -= 1
            if steps > 0:
                return 'unresolved', 'Attempted relative import beyond top-level package', None
            if imported.module:
                resolved_module = '.'.join(base + [imported.module]) if base else imported.module
            else:
                resolved_module = '.'.join(base)
        else:
            resolved_module = imported.module

        # Determine target module and member
        if imported.member is not None:
            submodule_candidate = f"{resolved_module}.{imported.member}" if resolved_module else imported.member
            if submodule_candidate in modules:
                # The imported member is itself a module (e.g. from core import validation as val)
                target_module_name = submodule_candidate
                if len(parts) != 2:
                    return 'unresolved', 'Submodule attribute call requires single member access', None
                member = parts[-1]
            else:
                # The imported member is a function or object inside resolved_module (e.g. from calc import add)
                target_module_name = resolved_module
                if len(parts) != 1:
                    return 'unresolved', 'Imported-object attribute calls are unsupported', None
                member = imported.member
        else:
            # Whole module import (e.g. import calc or import core.validation as val)
            target_module_name = resolved_module
            prefix = target_module_name.split('.') if binding.import_target != target_module_name else [binding.name]
            if parts[:-1] != prefix:
                return 'unresolved', 'Unsupported module attribute chain', None
            member = parts[-1]

        candidates = modules.get(target_module_name, [])
        if not candidates:
            if is_relative:
                return 'unresolved', 'Relative module target not found in snapshot', None
            return 'external', 'Explicit module is outside the supplied snapshot', None
        if len(candidates) > 1:
            return 'ambiguous', 'Multiple files identify the imported module', None
        module = candidates[0]
        if module is None:
            return 'unresolved', 'Imported module has no successful analysis', None
        target_lookup = module.symbol_table.lookup(module.module_scope_id, member)
        if not target_lookup.is_complete:
            return 'unresolved', 'Imported module scope is incomplete', None
        if len(target_lookup.bindings) > 1:
            return 'ambiguous', 'Imported name has multiple bindings', None
        if len(target_lookup.bindings) == 1:
            symbol = target_lookup.bindings[0]
            target = functions.get(symbol.function_id) if symbol.kind == 'function' else None
            if target:
                return 'resolved', 'Explicit import selects a unique module function', target
        return 'unresolved', 'No direct function export; re-exports are unsupported', None
