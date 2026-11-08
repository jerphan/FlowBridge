"""Data models for the hierarchical diagram renderer."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class HierarchicalFunction:
    """A function within a file."""
    function_id: str
    function_name: str
    qualified_name: str
    function_graph_id: str
    file_id: str
    start_line: int
    end_line: int


@dataclass
class HierarchicalFile:
    """A file within a project, containing functions."""
    file_id: str
    file_name: str
    file_path: str
    file_graph_id: str
    status: str = "complete"
    functions: List[HierarchicalFunction] = field(default_factory=list)


@dataclass
class HierarchicalProjectModel:
    """Organized, hierarchical view of a project's graphs."""
    project_id: str
    project_name: str
    project_graph_id: str
    files: List[HierarchicalFile] = field(default_factory=list)
    file_statuses: Dict[str, str] = field(default_factory=dict)
    
    # Fast lookups
    node_to_child_graph: Dict[str, str] = field(default_factory=dict)
    child_graph_to_parent: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    graph_to_source_file: Dict[str, str] = field(default_factory=dict)


@dataclass
class RenderedNode:
    """A laid-out node with physical coordinates and shape styling."""
    node_id: str
    label: str
    node_type: str  # 'start', 'end', 'condition', 'statement', 'function', 'return', 'file'
    x: float
    y: float
    width: float
    height: float
    source_location: Optional[Dict[str, Any]] = None
    target_graph_id: Optional[str] = None
    is_clickable: bool = False
    status: Optional[str] = None


@dataclass
class RenderedEdge:
    """A routed edge between two nodes."""
    edge_id: str
    source_id: str
    target_id: str
    edge_type: str  # 'next', 'true', 'false', 'back', 'return', 'exception'
    label: Optional[str] = None
    points: List[Tuple[float, float]] = field(default_factory=list)
    is_back_edge: bool = False


@dataclass
class RenderedGraph:
    """A fully rendered diagram ready for SVG or web presentation."""
    graph_id: str
    graph_type: str  # 'project', 'file', 'function'
    title: str
    width: float
    height: float
    nodes: List[RenderedNode] = field(default_factory=list)
    edges: List[RenderedEdge] = field(default_factory=list)
    svg_content: str = ""
