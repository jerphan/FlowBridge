"""One typed graph with local node/edge identities and validated ownership."""
from __future__ import annotations
from dataclasses import dataclass, field
from .JsonModel import GraphStatus, JsonModel, ViewType, _unique
from .FlowEdge import FlowEdge
from .FlowNode import FlowNode


@dataclass(kw_only=True, init=False)
class GraphModel(JsonModel):
    """Overview or function CFG, with local node and edge identities."""
    graph_id: str
    graph_type: ViewType
    status: GraphStatus
    file_id: str | None = None
    function_id: str | None = None
    nodes: list[FlowNode] = field(default_factory=list)
    edges: list[FlowEdge] = field(default_factory=list)

    def __init__(
        self, *, graph_id: str, status: GraphStatus,
        graph_type: ViewType | None = None, view_type: ViewType | None = None,
        file_id: str | None = None, function_id: str | None = None,
        nodes: list[FlowNode] | None = None, edges: list[FlowEdge] | None = None,
    ) -> None:
        """Create a graph; accept the former view_type keyword for compatibility.

        graph_type is the canonical field and serializes as graphType. Supplying
        conflicting old/new names is an error, rather than silently picking one.
        Omitted collections receive fresh lists for this graph.
        """
        if graph_type is None and view_type is None:
            raise TypeError('graph_type is required')
        if graph_type is not None and view_type is not None and graph_type != view_type:
            raise ValueError('graph_type and view_type disagree')
        self.graph_id = graph_id
        self.graph_type = graph_type if graph_type is not None else view_type
        self.status = status
        self.file_id = file_id
        self.function_id = function_id
        self.nodes = [] if nodes is None else nodes
        self.edges = [] if edges is None else edges
        self.__post_init__()

    @property
    def view_type(self) -> ViewType:
        """Return the former Python field name without duplicating graph state."""
        return self.graph_type

    @view_type.setter
    def view_type(self, value: ViewType) -> None:
        self.graph_type = value

    def __post_init__(self) -> None:
        """Validate child records, graph-local IDs, endpoints and owner fields."""
        super().__post_init__()
        _unique([node.node_id for node in self.nodes], 'node IDs')
        _unique([edge.edge_id for edge in self.edges], 'edge IDs')
        node_ids = {node.node_id for node in self.nodes}
        if any(edge.source_id not in node_ids or edge.target_id not in node_ids for edge in self.edges):
            raise ValueError('Edge endpoint does not exist in its graph')
        if self.status != 'complete' and (self.nodes or self.edges):
            raise ValueError('Unsupported/failed graphs must be empty')
        if self.graph_type == 'project' and (self.file_id is not None or self.function_id is not None):
            raise ValueError('Project graph cannot have file/function owners')
        if self.graph_type in ('file', 'function', 'module') and self.file_id is None:
            raise ValueError('File/function/module graph requires file_id')
        if (self.graph_type == 'function') != (self.function_id is not None):
            raise ValueError('Only function graphs require function_id')

