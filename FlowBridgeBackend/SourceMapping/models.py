"""Data models for the Source Mapping module."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SourceSpan:
    """Exact source text range in a Python file."""
    file_id: str
    file_path: str
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def contains_line(self, line_number: int) -> bool:
        return self.start_line <= line_number <= self.end_line

    def line_count(self) -> int:
        return max(1, self.end_line - self.start_line + 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fileId": self.file_id,
            "filePath": self.file_path,
            "startLine": self.start_line,
            "startColumn": self.start_column,
            "endLine": self.end_line,
            "endColumn": self.end_column,
        }


@dataclass
class NodeSourceMapping:
    """Mapping between a single flowchart node and its source code."""
    node_id: str
    graph_id: str
    node_type: str
    label: str
    span: Optional[SourceSpan] = None
    target_graph_id: Optional[str] = None
    target_file_id: Optional[str] = None
    target_function_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodeId": self.node_id,
            "graphId": self.graph_id,
            "nodeType": self.node_type,
            "label": self.label,
            "span": self.span.to_dict() if self.span else None,
            "targetGraphId": self.target_graph_id,
            "targetFileId": self.target_file_id,
            "targetFunctionName": self.target_function_name,
        }


@dataclass
class FileSourceIndex:
    """Index of nodes and line spans for a single Python file."""
    file_id: str
    file_path: str
    # Map of line_number -> list of node_ids covering that line
    line_to_nodes: Dict[int, List[str]] = field(default_factory=dict)
    # Map of node_id -> SourceSpan
    node_to_span: Dict[str, SourceSpan] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fileId": self.file_id,
            "filePath": self.file_path,
            "lineToNodes": {str(k): v for k, v in self.line_to_nodes.items()},
            "nodeToSpan": {k: v.to_dict() for k, v in self.node_to_span.items()},
        }


@dataclass
class BidirectionalProjectIndex:
    """Complete project source mapping index."""
    project_id: str
    files: Dict[str, FileSourceIndex] = field(default_factory=dict)
    nodes: Dict[str, NodeSourceMapping] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "projectId": self.project_id,
            "files": {k: v.to_dict() for k, v in self.files.items()},
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
        }
