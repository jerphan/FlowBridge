from .models import SourceLocation, SourceMapping


class SourceMappingLayer:
    """Find source ranges in one project's current mapping output."""

    def __init__(self, projectId: str | None = None):
        self.sourceMappings: list[SourceMapping] = []
        self.selectedGraphId: str | None = None
        self.selectedNodeId: str | None = None
        self.projectId = projectId
        self.revisionId: int | None = None

    def loadMappingOutput(self, output: dict) -> None:
        if not isinstance(output, dict):
            raise ValueError("Expected a MappingOutput object.")
        project_id = output.get("projectId")
        revision_id = output.get("revisionId")
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("Mapping output needs a projectId.")
        if type(revision_id) is not int or revision_id < 0:
            raise ValueError("Mapping output needs a nonnegative integer revisionId.")
        if self.projectId is not None and project_id != self.projectId:
            raise ValueError("Create a new mapping layer when switching projects.")
        if self.revisionId is not None and revision_id < self.revisionId:
            raise ValueError("Cannot replace mappings with an older revision.")
        self.updateMappings(output.get("sourceMappings"))
        self.projectId = project_id
        self.revisionId = revision_id

    def updateMappings(self, source_mappings: list) -> None:
        if not isinstance(source_mappings, list):
            raise ValueError("sourceMappings must be a list.")
        mappings = []
        seen = set()
        # Finish reading every entry before replacing the current mappings.
        for mapping in source_mappings:
            try:
                location = SourceLocation(**mapping["location"])
                entry = SourceMapping(
                    graphId=mapping["graphId"],
                    nodeId=mapping["nodeId"],
                    location=location,
                )
            except (KeyError, TypeError) as error:
                raise ValueError("Source mapping fields are missing or invalid.") from error
            key = (entry.graphId, entry.nodeId)
            if key in seen:
                raise ValueError("Duplicate graphId and nodeId in source mappings.")
            seen.add(key)
            mappings.append(entry)

        self.sourceMappings = mappings
        self.selectedGraphId = None
        self.selectedNodeId = None

    def findSourceMapping(
        self,
        graphId: str,
        nodeId: str,
    ) -> SourceMapping | None:
        for mapping in self.sourceMappings:
            if mapping.graphId == graphId and mapping.nodeId == nodeId:
                return mapping

        return None

    def getSourceLocation(
        self,
        graphId: str,
        nodeId: str,
    ) -> SourceLocation | None:
        mapping = self.findSourceMapping(graphId, nodeId)

        if mapping is None:
            return None

        return mapping.location
