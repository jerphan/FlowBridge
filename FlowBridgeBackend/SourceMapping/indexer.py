"""Builds bidirectional line-to-node and node-to-line indices."""
from typing import Any, Dict, List, Optional
from .models import BidirectionalProjectIndex, FileSourceIndex, NodeSourceMapping, SourceSpan


class SourceIndexer:
    """Constructs fast bidirectional lookup tables between code lines and flowchart nodes."""

    def build_project_index(
        self,
        project_id: str,
        flowchart_data: Dict[str, Any],
        project_files: List[Any],
    ) -> BidirectionalProjectIndex:
        index = BidirectionalProjectIndex(project_id=project_id)

        # File ID to file path lookup
        file_path_map: Dict[str, str] = {}
        for pf in project_files:
            fid = getattr(pf, "fileID", None) or getattr(pf, "fileId", None) or ""
            fpath = getattr(pf, "filePath", None) or getattr(pf, "fileName", None) or ""
            if fid:
                file_path_map[fid] = fpath
                index.files[fid] = FileSourceIndex(file_id=fid, file_path=fpath)

        # Graph references for cross-file links
        graph_refs = flowchart_data.get("graphReferences", [])
        ref_lookup: Dict[str, str] = {}  # source_node_id -> target_graph_id
        for ref in graph_refs:
            src_node = ref.get("sourceNodeId")
            tgt_graph = ref.get("targetGraphId")
            if src_node and tgt_graph:
                ref_lookup[src_node] = tgt_graph

        # Functions list for metadata resolution
        functions_data = flowchart_data.get("functions", [])
        func_by_graph: Dict[str, Any] = {}
        for fn in functions_data:
            gid = fn.get("graphId")
            if gid:
                func_by_graph[gid] = fn

        # Graphs collection
        graphs = flowchart_data.get("graphs", {})

        for graph_id, graph_data in graphs.items():
            graph_type = graph_data.get("graphType", "")
            file_id = graph_data.get("fileId", "")
            nodes = graph_data.get("nodes", [])

            for node in nodes:
                node_id = node.get("nodeId")
                if not node_id:
                    continue

                node_type = node.get("nodeType", "statement")
                label = node.get("label", "")
                loc_dict = node.get("sourceLocation")

                span: Optional[SourceSpan] = None
                if loc_dict:
                    node_file_id = loc_dict.get("fileId") or file_id
                    s_line = int(loc_dict.get("startLine", 1))
                    s_col = int(loc_dict.get("startColumn", 0))
                    e_line = int(loc_dict.get("endLine", s_line))
                    e_col = int(loc_dict.get("endColumn", 0))
                    f_path = file_path_map.get(node_file_id, "")

                    span = SourceSpan(
                        file_id=node_file_id,
                        file_path=f_path,
                        start_line=s_line,
                        start_column=s_col,
                        end_line=e_line,
                        end_column=e_col,
                    )

                    # Update file index
                    if node_file_id not in index.files:
                        index.files[node_file_id] = FileSourceIndex(file_id=node_file_id, file_path=f_path)
                    
                    file_idx = index.files[node_file_id]
                    file_idx.node_to_span[node_id] = span

                    for line_num in range(s_line, e_line + 1):
                        if line_num not in file_idx.line_to_nodes:
                            file_idx.line_to_nodes[line_num] = []
                        if node_id not in file_idx.line_to_nodes[line_num]:
                            file_idx.line_to_nodes[line_num].append(node_id)

                # Cross-file reference target info
                target_gid = ref_lookup.get(node_id)
                target_fid = None
                target_fname = None
                if target_gid and target_gid in func_by_graph:
                    fn_info = func_by_graph[target_gid]
                    target_fid = fn_info.get("fileId")
                    target_fname = fn_info.get("functionName")

                mapping = NodeSourceMapping(
                    node_id=node_id,
                    graph_id=graph_id,
                    node_type=node_type,
                    label=label,
                    span=span,
                    target_graph_id=target_gid,
                    target_file_id=target_fid,
                    target_function_name=target_fname,
                )
                index.nodes[node_id] = mapping

        return index
