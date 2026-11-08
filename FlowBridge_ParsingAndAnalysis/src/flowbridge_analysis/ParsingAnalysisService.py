"""Request-local orchestration of the static analysis pipeline."""
import ast
from .InputValidator import InputValidator, _decode_json
from .PythonParser import PythonParser
from .ASTAnalyzer import ASTAnalyzer
from .CFGBuilder import CFGBuilder
from .CallResolver import CallResolver
from .ProjectGraphBuilder import ProjectGraphBuilder
from .RevisionIds import RevisionIds
from .models import ProjectAnalysis, FileMetadata, FileInput, Diagnostic
from .ASTAnalyzer import ASTAnalysis


def _has_module_execution(tree: ast.Module) -> bool:
    for index, stmt in enumerate(tree.body):
        if index == 0 and isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
            continue
        if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
            continue
        return True
    return False


class ParsingAnalysisService:
    """Analyze one complete JSON snapshot entirely in memory."""

    def analyze_project(self, payload: str | dict[str, object]) -> ProjectAnalysis:
        """Rebuild a complete snapshot, retaining valid sibling files.

        There is no latest-result cache. Even an older revision or repeated request
        is analyzed from its supplied text. The caller owns revision ordering and
        must discard responses that do not match its current project/revision.
        """
        validation = InputValidator().validate(payload)
        if validation.project is None:
            identity = self._valid_identity(payload)
            return ProjectAnalysis(project_id=identity[0], project_name=identity[1], revision_id=identity[2],
                                   status='failed', diagnostics=validation.diagnostics)
        project = validation.project
        ids = RevisionIds(project.project_id, project.revision_id)
        # Fresh containers and fresh component workers prevent edited/deleted
        # functions, symbols or mappings from surviving a previous request.
        diagnostics = list(validation.diagnostics)
        files = []
        analyses = []
        functions = []
        symbols = []
        graphs = []
        mappings = []
        module_graphs = []
        module_graph_refs = []
        parsed_trees: dict[str, ast.Module] = {}
        for file in project.files:
            parsed = PythonParser().parse(file)
            diagnostics.extend(parsed.diagnostics)
            metadata = FileMetadata(file_id=file.file_id, file_name=file.file_name,
                file_path=file.file_path, graph_id=ids.make('graph', 'file', file.file_id),
                status='failed' if parsed.tree is None else 'complete')
            files.append(metadata)
            if parsed.tree is None:
                continue
            parsed_trees[file.file_id] = parsed.tree
            try:
                # ASTAnalyzer already invokes FeatureValidator; retain those diagnostics
                # once here rather than independently validating the same module again.
                analysis = ASTAnalyzer().analyze(parsed.tree, file, ids)
                analyses.append(analysis)
                functions.extend(analysis.functions)
                symbols.extend(analysis.symbol_table.symbols)
                diagnostics.extend(analysis.diagnostics)
                if any(d.severity == 'error' or d.code == 'INCOMPLETE_SCOPE' for d in analysis.diagnostics):
                    metadata.status = 'unsupported'
                for statement in parsed.tree.body:
                    if isinstance(statement, ast.FunctionDef):
                        built = CFGBuilder().build(statement, file, ids)
                        graphs.append(built.graph)
                        mappings.extend(built.source_mappings)
                        diagnostics.extend(built.diagnostics)
                        if built.graph.status != 'complete':
                            metadata.status = 'unsupported'
                if _has_module_execution(parsed.tree):
                    built_module = CFGBuilder().build_module(parsed.tree, file, ids)
                    module_graphs.append(built_module.graph)
                    mappings.extend(built_module.source_mappings)
                    diagnostics.extend(built_module.diagnostics)
                    module_graph_refs.extend(built_module.graph_references)
                    if built_module.graph.status != 'complete':
                        metadata.status = 'unsupported'
            except Exception as ex:
                metadata.status = 'failed'
                diagnostics.append(Diagnostic(
                    severity='error', code='INTERNAL_ANALYSIS_ERROR', file_id=file.file_id,
                    message=f'Unexpected error analyzing file {file.file_name}: {type(ex).__name__}: {ex}'))
        calls = CallResolver().resolve(project.files, analyses)
        import_dependencies = self._extract_import_dependencies(project.files, analyses)

        # Build complete File View CFGs for each file
        functions_by_id = {fn.function_id: fn for fn in functions}
        file_graphs = []
        file_graph_refs = []
        for file in project.files:
            tree = parsed_trees.get(file.file_id)
            if tree is None:
                continue
            local_functions = {
                stmt.name: stmt
                for stmt in tree.body
                if isinstance(stmt, ast.FunctionDef)
            }
            try:
                built_file = CFGBuilder().build_file(
                    tree, file, ids,
                    local_functions=local_functions,
                    functions_by_id=functions_by_id,
                    call_references=calls.call_references,
                )
                file_graphs.append(built_file.graph)
                mappings.extend(built_file.source_mappings)
                diagnostics.extend(built_file.diagnostics)
                file_graph_refs.extend(built_file.graph_references)
            except Exception as ex:
                diagnostics.append(Diagnostic(
                    severity='error', code='INTERNAL_ANALYSIS_ERROR', file_id=file.file_id,
                    message=f'Unexpected error building file view for {file.file_name}: {type(ex).__name__}: {ex}'))

        hierarchy = ProjectGraphBuilder().build(
            files, functions, graphs, ids,
            module_graphs=module_graphs,
            import_dependencies=import_dependencies,
            file_graphs=file_graphs
        )
        # Exact duplicates only are removed: graph-specific diagnostics remain
        # distinct from module inspection diagnostics because they identify views.
        unique_diagnostics = []
        seen = set()
        for diagnostic in diagnostics:
            key = diagnostic.to_json()
            if key not in seen:
                seen.add(key)
                unique_diagnostics.append(diagnostic)
        partial = any(file.status != 'complete' for file in files)
        result = ProjectAnalysis(project_id=project.project_id, project_name=project.project_name,
            revision_id=project.revision_id, status='partial' if partial else 'success',
            files=files, functions=functions, graphs=hierarchy.graphs, symbols=symbols,
            call_references=calls.call_references, source_mappings=mappings + hierarchy.source_mappings,
            graph_references=hierarchy.graph_references + module_graph_refs + file_graph_refs, diagnostics=unique_diagnostics)
        self._check_mapping_coverage(result)
        return result

    @staticmethod
    def _extract_import_dependencies(
        files: list[FileInput], analyses: list[ASTAnalysis]
    ) -> list[tuple[str, str]]:
        from pathlib import PurePosixPath

        modules: dict[str, str] = {}
        for file in files:
            path = PurePosixPath(file.file_path.replace('\\', '/'))
            if not path.name or path.suffix != '.py':
                continue
            parts = list(path.with_suffix('').parts)
            if not parts or not all(p.isidentifier() for p in parts):
                continue
            if parts[-1] == '__init__':
                parts.pop()
            if parts:
                mod_name = '.'.join(parts)
                modules[mod_name] = file.file_id

        dependencies: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for analysis in analyses:
            source_file_id = analysis.file_id
            source_file = next((f for f in files if f.file_id == source_file_id), None)
            source_parts: list[str] = []
            if source_file and source_file.file_path:
                try:
                    p = PurePosixPath(source_file.file_path.replace('\\', '/'))
                    if p.name and p.suffix:
                        source_parts = list(p.with_suffix('').parts)[:-1]
                    else:
                        source_parts = list(p.parts)[:-1]
                except ValueError:
                    source_parts = []

            for imp in analysis.imports:
                target_file_id = None
                if imp.level == 0:
                    if imp.module in modules:
                        target_file_id = modules[imp.module]
                    elif imp.member and f"{imp.module}.{imp.member}" in modules:
                        target_file_id = modules[f"{imp.module}.{imp.member}"]
                else:
                    base = list(source_parts)
                    lvl = imp.level - 1
                    while lvl > 0 and base:
                        base.pop()
                        lvl -= 1
                    rel_mod = '.'.join(base + ([imp.module] if imp.module else []))
                    if rel_mod in modules:
                        target_file_id = modules[rel_mod]
                    elif imp.member and f"{rel_mod}.{imp.member}" in modules:
                        target_file_id = modules[f"{rel_mod}.{imp.member}"]

                if target_file_id and target_file_id != source_file_id:
                    pair = (source_file_id, target_file_id)
                    if pair not in seen:
                        seen.add(pair)
                        dependencies.append(pair)
        return dependencies

    @staticmethod
    def _valid_identity(payload: str | dict[str, object]) -> tuple[str | None, str | None, int | None]:
        """Preserve individually valid identity fields in structural failure results."""
        if isinstance(payload, str):
            # Use the validator's strict decoder: duplicate identities must never
            # be silently accepted while preserving a failed request's revision.
            try:
                payload = _decode_json(payload)
            except (ValueError, RecursionError):
                return None, None, None
        if not isinstance(payload, dict):
            return None, None, None
        project_id = payload.get('projectId')
        project_name = payload.get('projectName')
        revision = payload.get('revisionId')
        return (project_id if isinstance(project_id, str) and project_id.strip() else None,
                project_name if isinstance(project_name, str) and project_name.strip() else None,
                revision if type(revision) is int and revision >= 0 else None)

    @staticmethod
    def _check_mapping_coverage(result: ProjectAnalysis) -> None:
        """Every source-backed node must have exactly one canonical mapping."""
        expected = {(graph.graph_id, node.node_id) for graph in result.graphs.values()
                    for node in graph.nodes if node.source_location is not None}
        actual = {(mapping.graph_id, mapping.node_id) for mapping in result.source_mappings}
        if expected != actual:
            raise ValueError('Incomplete source mapping coverage')

