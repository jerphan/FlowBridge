"""Structural project/file views linked to existing function CFGs."""
from dataclasses import dataclass, field
from .RevisionIds import RevisionIds
from .models import (FileInput, FileMetadata, FunctionInfo, GraphModel, FlowNode,
                     GraphReference, GraphStatus, SourceLocation, SourceMapping)


@dataclass
class ProjectGraphResult:
    """One hierarchy; existing function CFG objects are reused without new IDs."""
    project_graph: GraphModel
    file_graphs: dict[str, GraphModel]
    files: list[FileMetadata]
    graph_references: list[GraphReference] = field(default_factory=list)
    source_mappings: list[SourceMapping] = field(default_factory=list)
    function_graphs: dict[str, GraphModel] = field(default_factory=dict)
    module_graphs: dict[str, GraphModel] = field(default_factory=dict)

    @property
    def graphs(self) -> dict[str, GraphModel]:
        """Return all hierarchy graphs with collision checks."""
        combined = {self.project_graph.graph_id: self.project_graph}
        for collection in (self.file_graphs, self.function_graphs, self.module_graphs):
            for key, graph in collection.items():
                if key != graph.graph_id or key in combined:
                    raise ValueError('Graph identity collision')
                combined[key] = graph
        return combined

    def combine_graphs(self, function_graphs: dict[str, GraphModel]) -> dict[str, GraphModel]:
        """Retain compatibility with explicit assembly; never overwrite a graph."""
        combined = self.graphs
        for key, graph in function_graphs.items():
            if key != graph.graph_id or (key in combined and combined[key] is not graph):
                raise ValueError('Graph identity collision')
            combined[key] = graph
        return combined


# Both published names refer to the same result type.
ProjectGraphs = ProjectGraphResult


class ProjectGraphBuilder:
    """Build containment/navigation views without inventing execution edges."""

    def build(self, files: list[FileInput] | list[FileMetadata], functions: list[FunctionInfo],
              function_graphs: dict[str, GraphModel] | list[GraphModel], ids: RevisionIds,
              file_statuses: dict[str, GraphStatus] | None = None,
              project_status: GraphStatus = 'complete',
              module_graphs: dict[str, GraphModel] | list[GraphModel] | None = None) -> ProjectGraphResult:
        """Accept metadata or input files and validated existing function CFGs.

        Lists retain the service API; dictionaries retain the overview API.
        A complete overview describes containment, not module execution support.
        """
        if isinstance(function_graphs, list):
            graph_list = function_graphs
            function_graphs = {graph.graph_id: graph for graph in graph_list}
            if len(function_graphs) != len(graph_list):
                raise ValueError('Duplicate graph identity')
        mod_map: dict[str, GraphModel] = {}
        if module_graphs:
            if isinstance(module_graphs, list):
                mod_map = {g.graph_id: g for g in module_graphs}
                if len(mod_map) != len(module_graphs):
                    raise ValueError('Duplicate module graph identity')
            else:
                mod_map = dict(module_graphs)
        file_ids = {file.file_id for file in files}
        if len(file_ids) != len(files):
            raise ValueError('Duplicate file identity')
        if len({fn.function_id for fn in functions}) != len(functions):
            raise ValueError('Duplicate function identity')
        if set(function_graphs) != {fn.graph_id for fn in functions}:
            raise ValueError('Missing or unowned function graph')
        functions_by_file: dict[str, list[FunctionInfo]] = {}
        for function in functions:
            graph = function_graphs[function.graph_id]
            graph.__post_init__()
            if (function.file_id not in file_ids or graph.graph_id != function.graph_id
                    or graph.function_id != function.function_id or graph.file_id != function.file_id
                    or graph.graph_type != 'function'):
                raise ValueError('Function graph ownership mismatch')
            functions_by_file.setdefault(function.file_id, []).append(function)
        project = GraphModel(graph_id=ids.make('graph', 'project'), graph_type='project', status=project_status)
        result = ProjectGraphResult(project, {}, [], function_graphs=dict(function_graphs), module_graphs=mod_map)
        statuses = file_statuses or {}
        for file in files:
            file_graph_id = ids.make('graph', 'file', file.file_id)
            if isinstance(file, FileMetadata) and file.graph_id != file_graph_id:
                raise ValueError('File graph revision mismatch')
            status = statuses.get(file.file_id, file.status if isinstance(file, FileMetadata) else 'complete')
            metadata = FileMetadata(file_id=file.file_id, file_name=file.file_name,
                file_path=file.file_path, graph_id=file_graph_id, status=status)
            result.files.append(metadata)
            overview = GraphModel(graph_id=file_graph_id, graph_type='file', file_id=file.file_id,
                                  status='failed' if status == 'failed' else 'complete')
            result.file_graphs[file_graph_id] = overview
            # Noncomplete project graphs must be empty and cannot be reference sources.
            if project_status == 'complete':
                node = FlowNode(node_id=ids.make('node', project.graph_id, file.file_id),
                                node_type='file', label=file.file_name)
                project.nodes.append(node)
                result.graph_references.append(GraphReference(source_graph_id=project.graph_id,
                    source_node_id=node.node_id, target_graph_id=overview.graph_id))
            owned_functions = functions_by_file.get(file.file_id, [])
            if status == 'failed' and owned_functions:
                raise ValueError('Failed file cannot own extracted functions')
            for function in owned_functions:
                location = SourceLocation(file_id=file.file_id, start_line=function.start_line,
                    start_column=function.start_column, end_line=function.end_line,
                    end_column=function.end_column)
                node = FlowNode(node_id=ids.make('node', overview.graph_id, function.function_id),
                    node_type='function', label=function.function_name, source_location=location)
                overview.nodes.append(node)
                result.source_mappings.append(SourceMapping(graph_id=overview.graph_id,
                    node_id=node.node_id, location=location))
                result.graph_references.append(GraphReference(source_graph_id=overview.graph_id,
                    source_node_id=node.node_id, target_graph_id=function.graph_id))
            mod_graph = next((g for g in mod_map.values() if g.file_id == file.file_id), None)
            if mod_graph is not None and status != 'failed':
                node = FlowNode(node_id=ids.make('node', overview.graph_id, 'module'),
                                node_type='statement', label=f'{file.file_name} execution')
                overview.nodes.append(node)
                result.graph_references.append(GraphReference(source_graph_id=overview.graph_id,
                    source_node_id=node.node_id, target_graph_id=mod_graph.graph_id))
        for graph in result.graphs.values():
            graph.__post_init__()
        return result
