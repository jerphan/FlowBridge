"""Graph Organizer: normalizes raw analysis JSON into a hierarchical tree model."""
from typing import Any, Dict, List, Optional
from .models import HierarchicalProjectModel, HierarchicalFile, HierarchicalFunction


class GraphOrganizer:
    """Transforms flat analysis output into an indexed, hierarchical project model."""

    def organize(self, analysis_data: Dict[str, Any]) -> HierarchicalProjectModel:
        # Determine data shape (ProjectAnalysis vs FlowchartOutput)
        flowchart_data = analysis_data.get("flowchart", analysis_data)
        
        project_id = flowchart_data.get("projectId") or "unknown_project"
        project_name = flowchart_data.get("projectName") or "Unnamed Project"
        graphs = flowchart_data.get("graphs", {})
        graph_refs = flowchart_data.get("graphReferences", [])
        files_data = flowchart_data.get("files", [])
        functions_data = flowchart_data.get("functions", [])

        # Find project-level graph
        project_graph_id = ""
        for gid, g in graphs.items():
            if g.get("graphType") == "project":
                project_graph_id = gid
                break

        model = HierarchicalProjectModel(
            project_id=project_id,
            project_name=project_name,
            project_graph_id=project_graph_id,
        )

        # Build bidirectional lookups from graph references
        for ref in graph_refs:
            src_node = ref.get("sourceNodeId")
            src_graph = ref.get("sourceGraphId")
            tgt_graph = ref.get("targetGraphId")
            if src_node and tgt_graph:
                model.node_to_child_graph[src_node] = tgt_graph
            if src_graph and tgt_graph and src_node:
                model.child_graph_to_parent[tgt_graph] = (src_graph, src_node)

        # Map graph to source file
        for gid, g in graphs.items():
            fid = g.get("fileId")
            if fid:
                model.graph_to_source_file[gid] = fid

        # Group functions by file ID
        functions_by_file: Dict[str, List[HierarchicalFunction]] = {}
        for fn in functions_data:
            fid = fn.get("fileId")
            h_fn = HierarchicalFunction(
                function_id=fn.get("functionId", ""),
                function_name=fn.get("functionName", ""),
                qualified_name=fn.get("qualifiedName", fn.get("functionName", "")),
                function_graph_id=fn.get("graphId", ""),
                file_id=fid,
                start_line=fn.get("startLine", 0),
                end_line=fn.get("endLine", 0),
            )
            functions_by_file.setdefault(fid, []).append(h_fn)

        # Build HierarchicalFile entries
        for f in files_data:
            fid = f.get("fileId", "")
            fname = f.get("fileName", "")
            fpath = f.get("filePath", fname)
            fgraph_id = f.get("graphId", "")
            
            # If graphId not in file metadata, find file graph
            if not fgraph_id:
                for gid, g in graphs.items():
                    if g.get("graphType") == "file" and g.get("fileId") == fid:
                        fgraph_id = gid
                        break

            h_file = HierarchicalFile(
                file_id=fid,
                file_name=fname,
                file_path=fpath,
                file_graph_id=fgraph_id,
                functions=functions_by_file.get(fid, [])
            )
            model.files.append(h_file)

        return model
