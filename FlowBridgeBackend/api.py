"""HTTP routes for importing projects and retrieving their original source."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI, File, Form, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException

from .config import GitHubSettings, ImportLimits, RegistryLimits
from .diagram_renderer.runner import HierarchicalDiagramPipeline
from .errors import CodeManagerError, DiagramRenderError, SourceMappingNotFound
from .models import PyProject, SourceFile, SourceLocation
from .pipeline import FlowBridgePipeline
from .registry import ProjectRegistry
from .service import CodeManager
from .source_mapping import SourceMappingLayer
from .SourceMapping import SourceMappingService


# These models describe the request and error JSON exchanged with the UI.
class GitHubImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    url: str
    projectName: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    filePath: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class SourceSelection(BaseModel):
    projectId: str
    revisionId: int
    location: SourceLocation
    file: SourceFile


class RenderResponse(BaseModel):
    message: str = "Rendered hierarchical diagrams and interactive viewer."
    projectId: str
    revisionId: int
    status: str
    fileCount: int
    viewerUrl: str
    manifestUrl: str
    projectName: str
    projectGraphId: str
    graphs: dict[str, dict[str, Any]]
    flowchart: dict[str, Any]
    nodeToChildGraph: dict[str, str]
    childGraphToParent: dict[str, tuple[str, str]]
    graphToSourceFile: dict[str, str]
    sourceMapping: dict[str, Any]
    diagnostics: list[dict[str, Any]]
    analysisFiles: list[dict[str, Any]]
    analysisStatus: str


def get_registry(request: Request) -> ProjectRegistry:
    return request.app.state.registry


# Each import request gets a separate manager and its own current project.
def get_code_manager(request: Request) -> CodeManager:
    return CodeManager(
        limits=request.app.state.import_limits,
        github_settings=request.app.state.github_settings,
        github_client=request.app.state.github_client,
    )


# FastAPI supplies these arguments from the current request's app.
Registry = Annotated[ProjectRegistry, Depends(get_registry)]
Manager = Annotated[CodeManager, Depends(get_code_manager)]
ERROR_RESPONSES = {
    status: {"model": ErrorResponse} for status in (400, 404, 413, 422, 429, 500, 502, 503, 504)
}


# Each app owns its registry; blocking imports run in FastAPI's worker threads.
def create_app(
    *,
    import_limits: ImportLimits | None = None,
    registry_limits: RegistryLimits | None = None,
    github_settings: GitHubSettings | None = None,
    github_client: httpx.AsyncClient | None = None,
    render_root: Path | None = None,
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ),
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        Path(app.state.render_workspace.name).mkdir(parents=True, exist_ok=True)
        try:
            yield
        finally:
            app.state.registry.clear()
            app.state.render_workspace.cleanup()

    app = FastAPI(title="FlowBridge Code Manager", version="0.1.0", lifespan=lifespan)
    app.state.registry = ProjectRegistry(registry_limits)
    app.state.import_limits = import_limits or ImportLimits()
    app.state.github_settings = github_settings
    app.state.github_client = github_client

    if render_root is not None:
        render_root.mkdir(parents=True, exist_ok=True)
    app.state.render_workspace = TemporaryDirectory(prefix="flowbridge-diagrams-", dir=render_root)
    rendered_dir = Path(app.state.render_workspace.name)
    app.state.render_lock = Lock()
    app.mount("/viewer", StaticFiles(directory=str(rendered_dir), html=True), name="viewer")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(CodeManagerError)
    async def domain_error(request: Request, error: CodeManagerError) -> JSONResponse:
        return JSONResponse(error.payload(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": "Request fields are missing or invalid. Check the API documentation.",
                }
            },
            status_code=400,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "HTTP_ERROR",
                    "message": "The HTTP request could not be processed.",
                }
            },
            status_code=error.status_code,
            headers=error.headers,
        )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Each import route saves a complete project before returning it to the UI.
    @app.post("/api/projects/file", status_code=201, responses=ERROR_RESPONSES)
    def import_file(
        manager: Manager,
        registry: Registry,
        file: Annotated[UploadFile, File()],
        projectName: Annotated[str | None, Form()] = None,
    ) -> PyProject:
        manager.loadFile(file.file, fileName=file.filename or "", projectName=projectName)
        project = manager.getProject()
        registry.register(project)
        return project

    @app.post("/api/projects/zip", status_code=201, responses=ERROR_RESPONSES)
    def import_zip(
        manager: Manager,
        registry: Registry,
        file: Annotated[UploadFile, File()],
        projectName: Annotated[str | None, Form()] = None,
    ) -> PyProject:
        manager.loadZip(file.file, fileName=file.filename or "", projectName=projectName)
        project = manager.getProject()
        registry.register(project)
        return project

    @app.post("/api/projects/github", status_code=201, responses=ERROR_RESPONSES)
    def import_github(body: GitHubImportRequest, manager: Manager, registry: Registry) -> PyProject:
        manager.loadGit(body.url, projectName=body.projectName)
        project = manager.getProject()
        registry.register(project)
        return project

    @app.get("/api/projects/{projectID}", responses=ERROR_RESPONSES)
    def get_project(projectID: str, registry: Registry) -> PyProject:
        return registry.getProject(projectID)

    @app.get("/api/projects/{projectID}/files/{fileID}", responses=ERROR_RESPONSES)
    def get_file(projectID: str, fileID: str, registry: Registry) -> SourceFile:
        return registry.getSourceFile(projectID, fileID)

    # Parsing and Analysis integration routes
    @app.post("/api/projects/{projectID}/analyze", responses=ERROR_RESPONSES)
    def analyze_project(
        projectID: str, registry: Registry, revisionId: Annotated[int, Query(ge=0)] = 1
    ) -> dict[str, Any]:
        """Run full static analysis on the project, producing Flowchart and Mapping models."""
        project = registry.getProject(projectID)
        pipeline = FlowBridgePipeline()
        return pipeline.analyze_project(project, revision_id=revisionId)

    @app.get("/api/projects/{projectID}/flowchart", responses=ERROR_RESPONSES)
    def get_flowchart(
        projectID: str, registry: Registry, revisionId: Annotated[int, Query(ge=0)] = 1
    ) -> dict[str, Any]:
        """Retrieve Flowchart graph data for Kevin's UI visualizer."""
        project = registry.getProject(projectID)
        pipeline = FlowBridgePipeline()
        result = pipeline.analyze_project(project, revision_id=revisionId)
        return result["flowchart"]

    @app.get("/api/projects/{projectID}/mapping", responses=ERROR_RESPONSES)
    def get_mapping(
        projectID: str, registry: Registry, revisionId: Annotated[int, Query(ge=0)] = 1
    ) -> dict[str, Any]:
        """Retrieve Source Mapping data for Grace's code highlighting / navigation."""
        project = registry.getProject(projectID)
        pipeline = FlowBridgePipeline()
        result = pipeline.analyze_project(project, revision_id=revisionId)
        return result["mapping"]

    # A diagram node resolves to its original file and the parser's source range.
    @app.get("/api/projects/{projectID}/source-location", responses=ERROR_RESPONSES)
    def get_source_location(
        projectID: str,
        graphId: str,
        nodeId: str,
        registry: Registry,
        revisionId: Annotated[int, Query(ge=0)] = 1,
    ) -> SourceSelection:
        project = registry.getProject(projectID)
        result = FlowBridgePipeline().analyze_project(project, revision_id=revisionId)
        mappings = SourceMappingLayer(projectId=projectID)
        mappings.loadMappingOutput(result["mapping"])
        location = mappings.getSourceLocation(graphId, nodeId)
        if location is None:
            raise SourceMappingNotFound("This node has no source range in the selected revision.")
        return SourceSelection(
            projectId=projectID,
            revisionId=revisionId,
            location=location,
            file=registry.getSourceFile(projectID, location.fileId),
        )

    @app.post("/api/projects/{projectID}/render", responses=ERROR_RESPONSES)
    def render_project_diagrams(
        projectID: str, registry: Registry, revisionId: Annotated[int, Query(ge=0)] = 1
    ) -> RenderResponse:
        """Export one immutable project/revision without overwriting another project's diagrams."""
        project = registry.getProject(projectID)
        result = FlowBridgePipeline().analyze_project(project, revision_id=revisionId)
        destination = rendered_dir / project.projectID / str(revisionId)
        prefix = f"/viewer/{project.projectID}/{revisionId}"
        try:
            with app.state.render_lock:
                if not (destination / "index.html").is_file():
                    # Publish completed exports together; failed renders stay in a temporary folder.
                    with TemporaryDirectory(dir=rendered_dir) as staging:
                        renderer = HierarchicalDiagramPipeline(output_dir=staging)
                        model = renderer.run(result)
                        source_index = SourceMappingService().build_project_index(
                            project_id=project.projectID,
                            flowchart_data=result["flowchart"],
                            project_files=project.files,
                        )
                        response = RenderResponse(
                            projectId=project.projectID,
                            revisionId=revisionId,
                            status=result["status"],
                            fileCount=len(project.files),
                            viewerUrl=f"{prefix}/",
                            manifestUrl=f"{prefix}/manifest.json",
                            projectName=project.projectName,
                            projectGraphId=model.project_graph_id,
                            graphs={
                                graph.graph_id: {
                                    "id": graph.graph_id, "type": graph.graph_type,
                                    "title": graph.title, "svg": graph.svg_content,
                                    "width": graph.width, "height": graph.height,
                                }
                                for graph in renderer.rendered_graphs
                            },
                            flowchart=result["flowchart"],
                            nodeToChildGraph={
                                node: target for (_, node), target in model.node_to_child_graph.items()
                            },
                            childGraphToParent=model.child_graph_to_parent,
                            graphToSourceFile=model.graph_to_source_file,
                            sourceMapping=source_index.to_dict(),
                            diagnostics=result["analysis"]["diagnostics"],
                            analysisFiles=result["analysis"]["files"],
                            analysisStatus=result["status"],
                        )
                        (Path(staging) / "response.json").write_text(
                            response.model_dump_json(), encoding="utf-8"
                        )
                        destination.parent.mkdir(exist_ok=True)
                        Path(staging).rename(destination)
        except (OSError, ValueError) as error:
            raise DiagramRenderError(
                "The diagrams could not be exported. Please try again."
            ) from error
        return RenderResponse.model_validate_json(
            (destination / "response.json").read_text(encoding="utf-8")
        )

    return app


app = create_app()
