from threading import Lock

from .config import RegistryLimits
from .errors import DuplicateFile, ProjectNotFound, RegistryCapacityExceeded
from .models import PyProject, SourceFile


# The registry keeps saved projects available across separate import requests.
class ProjectRegistry:
    def __init__(self, limits: RegistryLimits | None = None) -> None:
        self.limits = limits or RegistryLimits()
        self._projects: dict[str, PyProject] = {}
        self._text_bytes = 0
        self._lock = Lock()

    def register(self, project: PyProject) -> None:
        # Store a validated copy so caller changes cannot bypass the byte limit.
        snapshot = PyProject.model_validate(project.model_dump())
        size = sum(len(file.fileContent.encode("utf-8")) for file in snapshot.files)
        with self._lock:
            if snapshot.projectID in self._projects:
                raise DuplicateFile("A project with that ID is already registered.")
            if size > self.limits.max_text_bytes:
                raise RegistryCapacityExceeded(
                    "This project exceeds the session storage limit. Import a smaller project."
                )
            # Make room only after the new snapshot has passed validation and size checks.
            while (len(self._projects) >= self.limits.max_projects
                   or self._text_bytes + size > self.limits.max_text_bytes):
                oldest = next(iter(self._projects))
                removed = self._projects.pop(oldest)
                self._text_bytes -= sum(len(file.fileContent.encode("utf-8")) for file in removed.files)
            self._projects[snapshot.projectID] = snapshot
            self._text_bytes += size

    # Return a copy so later changes cannot alter the saved project.
    def getProject(self, projectID: str) -> PyProject:
        with self._lock:
            project = self._find(projectID)
            return project.model_copy(deep=True)

    # Look up the file inside the requested project, using both IDs.
    def getSourceFile(self, projectID: str, fileID: str) -> SourceFile:
        with self._lock:
            return self._find(projectID).getFileByID(fileID)

    def _find(self, projectID: str) -> PyProject:
        project = self._projects.get(projectID)
        if project is None:
            raise ProjectNotFound("No retained project has that ID. Re-import it to continue.")
        # Accessed projects stay recent, so an active workspace is retained ahead of idle ones.
        self._projects.pop(projectID)
        self._projects[projectID] = project
        return project

    def clear(self) -> None:
        with self._lock:
            self._projects.clear()
            self._text_bytes = 0
