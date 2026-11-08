"""Query and resolution engine for source mapping lookups."""
from typing import List, Optional, Tuple
from .models import BidirectionalProjectIndex, NodeSourceMapping, SourceSpan


class SourceResolver:
    """Answers queries for node-to-source and line-to-node lookups."""

    def __init__(self, index: BidirectionalProjectIndex) -> None:
        self.index = index

    def get_span_for_node(self, node_id: str) -> Optional[SourceSpan]:
        """Returns the source code span for a given flowchart node."""
        node_mapping = self.index.nodes.get(node_id)
        return node_mapping.span if node_mapping else None

    def get_nodes_for_line(self, file_id: str, line_number: int) -> List[NodeSourceMapping]:
        """Returns flowchart nodes that cover a specific source code line.
        
        Results are sorted by span size ascending (most specific statement first).
        """
        file_idx = self.index.files.get(file_id)
        if not file_idx:
            return []

        node_ids = file_idx.line_to_nodes.get(line_number, [])
        nodes: List[NodeSourceMapping] = []
        for nid in node_ids:
            if nid in self.index.nodes:
                nodes.append(self.index.nodes[nid])

        # Sort so tightest span comes first
        nodes.sort(key=lambda n: n.span.line_count() if n.span else 999999)
        return nodes

    def get_cross_file_target(self, node_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Returns (target_graph_id, target_file_id, target_function_name) for a call node."""
        node_mapping = self.index.nodes.get(node_id)
        if not node_mapping:
            return (None, None, None)
        return (
            node_mapping.target_graph_id,
            node_mapping.target_file_id,
            node_mapping.target_function_name,
        )
