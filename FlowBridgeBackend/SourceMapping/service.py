"""High-level service orchestrating source mapping operations."""
from typing import Any, Dict, List
from .indexer import SourceIndexer
from .models import BidirectionalProjectIndex
from .resolver import SourceResolver


class SourceMappingService:
    """Service providing source mapping indices for FlowBridge projects."""

    def __init__(self) -> None:
        self.indexer = SourceIndexer()

    def build_project_index(
        self,
        project_id: str,
        flowchart_data: Dict[str, Any],
        project_files: List[Any],
    ) -> BidirectionalProjectIndex:
        """Constructs the bidirectional index from analysis output and source files."""
        return self.indexer.build_project_index(project_id, flowchart_data, project_files)

    def create_resolver(self, index: BidirectionalProjectIndex) -> SourceResolver:
        """Instantiates a query resolver for an index."""
        return SourceResolver(index)
