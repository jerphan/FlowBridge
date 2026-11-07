"""Request-local orchestration of the static analysis pipeline."""
import ast
from .InputValidator import InputValidator, _decode_json
from .PythonParser import PythonParser
from .ASTAnalyzer import ASTAnalyzer
from .CFGBuilder import CFGBuilder
from .CallResolver import CallResolver
from .ProjectGraphBuilder import ProjectGraphBuilder
from .RevisionIds import RevisionIds
from .models import ProjectAnalysis, FileMetadata, Diagnostic


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
        for file in project.files:
            parsed = PythonParser().parse(file)
            diagnostics.extend(parsed.diagnostics)
            metadata = FileMetadata(file_id=file.file_id, file_name=file.file_name,
                file_path=file.file_path, graph_id=ids.make('graph', 'file', file.file_id),
                status='failed' if parsed.tree is None else 'complete')
            files.append(metadata)
            if parsed.tree is None:
                continue
            try:
                # ASTAnalyzer already invokes FeatureValidator; retain those diagnostics
                # once here rather than independently validating the same module again.
                analysis = ASTAnalyzer().analyze(parsed.tree, file, ids)
                file_graphs = []
                file_mappings = []
                file_diagnostics = list(analysis.diagnostics)
                built_module = None
                if any(d.severity == 'error' or d.code == 'INCOMPLETE_SCOPE' for d in analysis.diagnostics):
                    metadata.status = 'unsupported'
                for statement in parsed.tree.body:
                    if isinstance(statement, ast.FunctionDef):
                        built = CFGBuilder().build(statement, file, ids)
                        file_graphs.append(built.graph)
                        file_mappings.extend(built.source_mappings)
                        file_diagnostics.extend(built.diagnostics)
                        if built.graph.status != 'complete':
                            metadata.status = 'unsupported'
                if _has_module_execution(parsed.tree):
                    built_module = CFGBuilder().build_module(parsed.tree, file, ids)
                    file_mappings.extend(built_module.source_mappings)
                    file_diagnostics.extend(built_module.diagnostics)
                    if built_module.graph.status != 'complete':
                        metadata.status = 'unsupported'
            except Exception as ex:
                metadata.status = 'failed'
                diagnostics.append(Diagnostic(
                    severity='error', code='INTERNAL_ANALYSIS_ERROR', file_id=file.file_id,
                    message=f'Unexpected error analyzing file {file.file_name}: {type(ex).__name__}: {ex}'))
                continue
            # Publish this file together so a failure cannot leave dangling graphs or mappings.
            analyses.append(analysis)
            functions.extend(analysis.functions)
            symbols.extend(analysis.symbol_table.symbols)
            graphs.extend(file_graphs)
            mappings.extend(file_mappings)
            diagnostics.extend(file_diagnostics)
            if built_module is not None:
                module_graphs.append(built_module.graph)
                module_graph_refs.extend(built_module.graph_references)
        calls = CallResolver().resolve(project.files, analyses)
        hierarchy = ProjectGraphBuilder().build(files, functions, graphs, ids, module_graphs=module_graphs)
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
            graph_references=hierarchy.graph_references + module_graph_refs, diagnostics=unique_diagnostics)
        self._check_mapping_coverage(result)
        return result

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

