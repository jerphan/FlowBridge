import { useState } from "react";
import axios from "axios";
import UploadModal from "./components/UploadModal";
import ExportModal from "./components/ExportModal";
import StartButton from "./components/StartButton";
import SourceCodeViewer from "./components/SourceCodeViewer";
import FlowchartCanvas from "./components/FlowchartCanvas";
import {
  BreadcrumbItem,
  FunctionInfo,
  PyProject,
  SourceFile,
  SourceMappingPayload,
} from "./types/flowchart";
import "./App.css";

const API_BASE_URL = "http://localhost:8000";

interface RenderedGraphDto {
  id: string;
  type: "project" | "file" | "function";
  title: string;
  svg: string;
  width: number;
  height: number;
}

interface RenderResponse {
  status: string;
  message: string;
  projectName: string;
  projectGraphId: string;
  fileCount: number;
  viewerUrl: string;
  graphs: Record<string, RenderedGraphDto>;
  flowchart: {
    files: Array<{ fileId: string; fileName: string; graphId: string }>;
    functions: FunctionInfo[];
    graphs: Record<string, { graphId: string; nodes: Array<{ nodeId: string; sourceLocation?: { startLine: number; endLine: number; fileId?: string } }> }>;
  };
  nodeToChildGraph: Record<string, string>;
  childGraphToParent: Record<string, [string, string]>;
  graphToSourceFile: Record<string, string>;
  sourceMapping?: SourceMappingPayload;
}

function getFileId(file?: SourceFile | null): string {
  if (!file) return "";
  return file.fileID || file.fileId || "";
}

function getFileName(file?: SourceFile | null): string {
  if (!file) return "";
  return file.fileName || file.filePath || file.path || "";
}

function App() {
  const [project, setProject] = useState<PyProject | null>(null);
  const [renderData, setRenderData] = useState<RenderResponse | null>(null);
  const [activeGraphId, setActiveGraphId] = useState<string | null>(null);
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);
  const [activeFile, setActiveFile] = useState<SourceFile | null>(null);
  const [activeFunction, setActiveFunction] = useState<FunctionInfo | null>(null);
  const [highlightedLines, setHighlightedLines] = useState<[number, number] | null>(null);
  const [highlightedNodeId, setHighlightedNodeId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Modals state
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState<boolean>(false);

  // 1. Handle Project Uploaded from UploadModal
  function handleProjectLoaded(uploadedProject: PyProject) {
    setProject(uploadedProject);
    setRenderData(null);
    setActiveGraphId(null);
    setBreadcrumbs([]);
    setErrorMessage(null);
    setHighlightedLines(null);
    setHighlightedNodeId(null);

    // Default to the first file if available
    if (uploadedProject.files && uploadedProject.files.length > 0) {
      setActiveFile(uploadedProject.files[0]);
    } else {
      setActiveFile(null);
    }
  }

  // 2. Handle Generate Flowchart via StartButton
  async function handleStartGeneration() {
    if (!project) return;

    const projectId = project.projectID || project.id;
    if (!projectId) {
      setErrorMessage("No project ID found. Please upload the project again.");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const response = await axios.post<RenderResponse>(
        `${API_BASE_URL}/api/projects/${projectId}/render`
      );

      const data = response.data;
      setRenderData(data);

      // Start at Level 1: Project View
      const projGraphId = data.projectGraphId;
      setActiveGraphId(projGraphId);

      setBreadcrumbs([
        {
          id: projGraphId,
          label: "Project View",
          type: "project",
        },
      ]);

      // In Project View, show all files overview
      setActiveFile(null);
      setActiveFunction(null);
      setHighlightedLines(null);
      setHighlightedNodeId(null);
    } catch (err: unknown) {
      console.error("Failed to generate diagrams:", err);
      const msg =
        axios.isAxiosError(err) && err.response?.data?.error?.message
          ? err.response.data.error.message
          : "Failed to generate diagrams. Check server logs.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }

  // 3. Handle Flowchart Node Click (Drill-Down & Source Sync)
  function handleNodeClick(nodeId: string) {
    if (!renderData) return;

    // Check if node triggers drill-down navigation
    const childGraphId = renderData.nodeToChildGraph[nodeId];

    if (childGraphId && renderData.graphs[childGraphId]) {
      const childGraph = renderData.graphs[childGraphId];
      navigateToGraph(childGraphId, childGraph.title, childGraph.type);
      return;
    }

    setHighlightedNodeId(nodeId);

    // Source mapping lookup for node
    const nodeMapping = renderData.sourceMapping?.nodes?.[nodeId];
    if (nodeMapping?.span) {
      if (nodeMapping.span.fileId && project && getFileId(activeFile) !== nodeMapping.span.fileId) {
        const targetFile = project.files.find((f) => getFileId(f) === nodeMapping.span!.fileId);
        if (targetFile) {
          setActiveFile(targetFile);
          setActiveFunction(null);
        }
      }
      setHighlightedLines([nodeMapping.span.startLine, nodeMapping.span.endLine]);
      return;
    }

    // Fallback: check raw graph sourceLocation
    if (activeGraphId && renderData.flowchart.graphs[activeGraphId]) {
      const rawGraph = renderData.flowchart.graphs[activeGraphId];
      const foundNode = rawGraph.nodes.find((n) => n.nodeId === nodeId);
      if (foundNode && foundNode.sourceLocation) {
        setHighlightedLines([
          foundNode.sourceLocation.startLine,
          foundNode.sourceLocation.endLine,
        ]);
      }
    }
  }

  // 4. Handle Source Code Line Click -> Highlight Flowchart Node
  function handleLineClick(lineNumber: number, fileId: string) {
    if (!renderData) return;

    setHighlightedLines([lineNumber, lineNumber]);

    // Check source mapping index for this line
    const fileIndex = renderData.sourceMapping?.files?.[fileId];
    const candidateNodes = fileIndex?.lineToNodes?.[String(lineNumber)];

    if (candidateNodes && candidateNodes.length > 0) {
      // Prioritize nodes present in the current active graph
      const activeNodes = candidateNodes.filter(
        (nid) => renderData.sourceMapping?.nodes?.[nid]?.graphId === activeGraphId
      );
      const chosenNodeId = activeNodes.length > 0 ? activeNodes[0] : candidateNodes[0];
      setHighlightedNodeId(chosenNodeId);
    }
  }

  // 5. Navigate to a specific graph (Project, File, or Function)
  function navigateToGraph(
    graphId: string,
    label: string,
    type: "project" | "file" | "function",
    fileIdOverride?: string
  ) {
    if (!renderData || !project) return;

    setActiveGraphId(graphId);
    setHighlightedLines(null);
    setHighlightedNodeId(null);

    // Update breadcrumbs
    const existingIndex = breadcrumbs.findIndex((b) => b.id === graphId);
    if (existingIndex !== -1) {
      setBreadcrumbs(breadcrumbs.slice(0, existingIndex + 1));
    } else {
      setBreadcrumbs((prev) => [
        ...prev,
        { id: graphId, label, type, fileId: fileIdOverride },
      ]);
    }

    if (type === "project") {
      setActiveFile(null);
      setActiveFunction(null);
    } else if (type === "file") {
      const targetFileId =
        fileIdOverride ||
        renderData.graphToSourceFile[graphId] ||
        renderData.flowchart.files.find((f) => f.graphId === graphId)?.fileId;

      const file = project.files.find(
        (f) => getFileId(f) === targetFileId || f.fileName === label || f.filePath === label
      );
      if (file) {
        setActiveFile(file);
      }
      setActiveFunction(null);
    } else if (type === "function") {
      const fnInfo = renderData.flowchart.functions.find(
        (fn) => fn.graphId === graphId
      );
      if (fnInfo) {
        setActiveFunction(fnInfo);
        const file = project.files.find((f) => getFileId(f) === fnInfo.fileId);
        if (file) {
          setActiveFile(file);
        }
      }
    }
  }

  // 6. Handle Breadcrumb Navigation Click
  function handleBreadcrumbClick(item: BreadcrumbItem, index: number) {
    setBreadcrumbs((prev) => prev.slice(0, index + 1));
    setActiveGraphId(item.id);
    setHighlightedLines(null);
    setHighlightedNodeId(null);

    if (item.type === "project") {
      setActiveFile(null);
      setActiveFunction(null);
    } else if (item.type === "file") {
      if (item.fileId && project) {
        const f = project.files.find((file) => getFileId(file) === item.fileId);
        if (f) setActiveFile(f);
      }
      setActiveFunction(null);
    } else if (item.type === "function") {
      if (renderData && project) {
        const fnInfo = renderData.flowchart.functions.find(
          (fn) => fn.graphId === item.id
        );
        if (fnInfo) {
          setActiveFunction(fnInfo);
          const f = project.files.find((file) => getFileId(file) === fnInfo.fileId);
          if (f) setActiveFile(f);
        }
      }
    }
  }

  // 7. Handle File Selection from Project List
  function handleFileSelect(file: SourceFile) {
    setActiveFile(file);
    setActiveFunction(null);
    setHighlightedLines(null);
    setHighlightedNodeId(null);

    if (renderData) {
      const fId = getFileId(file);
      const fMeta = renderData.flowchart.files.find((f) => f.fileId === fId);
      if (fMeta && renderData.graphs[fMeta.graphId]) {
        navigateToGraph(fMeta.graphId, fMeta.fileName, "file", fId);
      }
    }
  }

  // Active diagram SVG
  const activeSvg =
    renderData && activeGraphId && renderData.graphs[activeGraphId]
      ? renderData.graphs[activeGraphId].svg
      : null;

  const currentTitle =
    activeGraphId && renderData?.graphs[activeGraphId]
      ? renderData.graphs[activeGraphId].title
      : "Flowchart";

  return (
    <>
      <header className="heading">
        <div className="headingLeft">
          <img src="./FlowBridgeIcon.png" alt="Logo Icon" className="logoIcon" />
          <span className="brandName">FlowBridge</span>
        </div>

        <StartButton
          onClick={handleStartGeneration}
          disabled={!project}
          isLoading={isLoading}
        />

        <div className="headingRight">
          <div className="user-profile" title="User Profile">
            <div>
              <label htmlFor="loginButton">
                <img src="./ProfilePicture.png" alt="Profile Icon" className="loginIcon" />
              </label>
              <input type="button" id="loginButton" className="toolButton" />
            </div>
          </div>
        </div>
      </header>

      <div className="workspace">
        {/* Left Toolbar */}
        <aside className="sidebarLeft">
          <div className="toolbarTop">
            {/* Upload Button: Opens options modal */}
            <button
              onClick={() => setIsUploadModalOpen(true)}
              className="sidebarIconButton"
              title="Upload a Python file, ZIP project, or enter a public GitHub repository link."
            >
              <img src="UploadFileButton.png" alt="Upload Icon" className="toolIcon" />
            </button>

            {/* Export Button: Opens options modal */}
            <button
              onClick={() => setIsExportModalOpen(true)}
              className="sidebarIconButton"
              title={activeSvg ? "Export Diagram (SVG, PNG, PDF)" : "Generate a diagram to export"}
              disabled={!activeSvg}
              style={{ opacity: activeSvg ? 1 : 0.4 }}
            >
              <img src="ExportButton.png" alt="Export Icon" className="toolIcon" />
            </button>
          </div>

          <div className="toolbar-bottom">
            <button
              className="sidebarIconButton"
              title="Settings"
              onClick={() => alert("FlowBridge v1.0 — Ready & Connected to Backend.")}
            >
              <img src="SettingsIcon.png" alt="Settings Icon" className="toolIcon" />
            </button>
          </div>
        </aside>

        {/* Content Grid */}
        <main className="contentGrid">
          {/* Left Card: Source Code */}
          <section className="card">
            <div className="cardHeader">
              {activeFunction
                ? `⚡ ${activeFunction.functionName}() (Lines ${activeFunction.startLine}-${activeFunction.endLine})`
                : activeFile
                ? `📄 ${getFileName(activeFile)}`
                : project
                ? `🌐 ${project.projectName || project.name}`
                : "Source Code"}
            </div>

            <div className="cardBody">
              <SourceCodeViewer
                activeFile={activeFile}
                activeFunction={activeFunction}
                highlightedLines={highlightedLines}
                allFiles={project?.files || []}
                onSelectFile={handleFileSelect}
                onLineClick={handleLineClick}
                onBackToProjectFiles={() => {
                  setActiveFile(null);
                  setActiveFunction(null);
                  setHighlightedLines(null);
                  setHighlightedNodeId(null);
                  if (renderData) {
                    setActiveGraphId(renderData.projectGraphId);
                    setBreadcrumbs([{ id: renderData.projectGraphId, label: "Project View", type: "project" }]);
                  }
                }}
              />
            </div>
          </section>

          {/* Right Card: Flowchart Canvas */}
          <section className="card">
            <div className="cardHeader">
              <div style={{ fontSize: "16px", fontWeight: "bold" }}>FlowChart</div>

              {/* Breadcrumb Navigation Trail */}
              {breadcrumbs.length > 0 && (
                <div className="breadcrumbBar">
                  {breadcrumbs.map((b, idx) => {
                    const isLast = idx === breadcrumbs.length - 1;
                    return (
                      <span key={b.id} style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
                        <span
                          className={`breadcrumbItem ${isLast ? "breadcrumbActive" : ""}`}
                          onClick={() => handleBreadcrumbClick(b, idx)}
                          title={`Navigate to ${b.label}`}
                        >
                          {b.type === "project" ? "🌐 " : b.type === "file" ? "📄 " : "⚡ "}
                          {b.label}
                        </span>
                        {!isLast && <span className="breadcrumbSeparator">›</span>}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="cardBody flowchartBody">
              {errorMessage ? (
                <div style={{ color: "#d32f2f", textAlign: "center", padding: "20px" }}>
                  <p style={{ fontWeight: 600 }}>Error</p>
                  <p style={{ fontSize: "13px" }}>{errorMessage}</p>
                </div>
              ) : (
                <FlowchartCanvas
                  svgContent={activeSvg}
                  isLoading={isLoading}
                  onNodeClick={handleNodeClick}
                  title={currentTitle}
                  highlightedNodeId={highlightedNodeId}
                  viewType={breadcrumbs.length > 0 ? breadcrumbs[breadcrumbs.length - 1].type : "project"}
                />
              )}
            </div>
          </section>
        </main>
      </div>

      {/* Upload Modal */}
      <UploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onProjectLoaded={handleProjectLoaded}
        apiBaseUrl={API_BASE_URL}
      />

      {/* Export Modal */}
      <ExportModal
        isOpen={isExportModalOpen}
        onClose={() => setIsExportModalOpen(false)}
        svgContent={activeSvg}
        diagramTitle={currentTitle}
      />
    </>
  );
}

export default App;
