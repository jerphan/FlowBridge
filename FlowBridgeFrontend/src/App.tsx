import { useState, useMemo, useRef, useEffect } from "react";
import axios from "axios";
import {REQUEST_TIMEOUT_MS, errorMessage as requestError} from "./api";
import UploadModal from "./components/UploadModal";
import ExportModal from "./components/ExportModal";
import StartButton from "./components/StartButton";
import SourceCodeViewer from "./components/SourceCodeViewer";
import FlowchartCanvas from "./components/FlowchartCanvas";
import WorkspaceDialog from "./components/WorkspaceDialog";
import {
  BreadcrumbItem,
  FunctionInfo,
  PyProject,
  SourceFile,
  SourceMappingPayload,
  DiagnosticDto,
  FileMetadata,
  SourceLocation,
} from "./types/flowchart";
import "./App.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

interface RenderedGraphDto {
  id: string;
  type: "project" | "file" | "function";
  title: string;
  svg: string;
  width: number;
  height: number;
}

interface RenderResponse {
  projectId: string;
  revisionId: number;
  status: string;
  message: string;
  projectName: string;
  projectGraphId: string;
  fileCount: number;
  viewerUrl: string;
  graphs: Record<string, RenderedGraphDto>;
  flowchart: {
    files: Array<{ fileId: string; fileName: string; graphId: string; status?: "complete" | "unsupported" | "failed" }>;
    functions: FunctionInfo[];
    graphs: Record<string, { graphId: string; nodes: Array<{ nodeId: string; sourceLocation?: { startLine: number; endLine: number; fileId?: string } }> }>;
  };
  nodeToChildGraph: Record<string, string>;
  childGraphToParent: Record<string, [string, string]>;
  graphToSourceFile: Record<string, string>;
  sourceMapping?: SourceMappingPayload;
  diagnostics?: DiagnosticDto[];
  analysisFiles?: FileMetadata[];
  analysisStatus?: string;
}

interface ClassifiedDiagnostic {
  category: "Unsupported Python Feature" | "Syntax Error" | "Analysis Error" | "Resolution Warning";
  featureName: string;
  message: string;
  fileName: string;
  line?: number;
  severity: "error" | "warning" | "info";
  tip?: string;
}

function getFileId(file?: SourceFile | null): string {
  if (!file) return "";
  return file.fileID || file.fileId || "";
}

function getFileName(file?: SourceFile | null): string {
  if (!file) return "";
  return file.filePath || file.path || file.fileName || "";
}

function classifyDiagnostic(diag: DiagnosticDto, fileName: string): ClassifiedDiagnostic {
  const rawMsg = diag.message || "";
  const code = diag.code || "";
  const line = diag.sourceLocation?.startLine;

  if (code === "UNSUPPORTED_FEATURE") {
    if (rawMsg.includes("ClassDef") || rawMsg.toLowerCase().includes("class")) {
      return {
        category: "Unsupported Python Feature",
        featureName: "Class Definition",
        message: "Class definitions and object-oriented programming are not currently supported by FlowBridge.",
        fileName,
        line,
        severity: "error",
        tip: "FlowBridge models procedural and functional control flow. Consider refactoring classes into standard functions and modules.",
      };
    }
    if (rawMsg.includes("AsyncFunctionDef") || rawMsg.includes("async")) {
      return {
        category: "Unsupported Python Feature",
        featureName: "Asynchronous Function",
        message: "Asynchronous functions (async def) and coroutines are not currently supported by FlowBridge.",
        fileName,
        line,
        severity: "error",
        tip: "Convert async def functions into standard synchronous functions.",
      };
    }
    if (rawMsg.includes("Lambda") || rawMsg.toLowerCase().includes("lambda")) {
      return {
        category: "Unsupported Python Feature",
        featureName: "Lambda Expression",
        message: "Anonymous lambda expressions are not currently supported by FlowBridge.",
        fileName,
        line,
        severity: "error",
        tip: "Define standard named functions using def instead.",
      };
    }
    if (rawMsg.includes("Comp") || rawMsg.includes("GeneratorExp") || rawMsg.includes("comprehension")) {
      return {
        category: "Unsupported Python Feature",
        featureName: "Comprehension / Generator Expression",
        message: "Comprehensions and generator expressions are not currently supported by FlowBridge.",
        fileName,
        line,
        severity: "error",
        tip: "Rewrite comprehensions as explicit for-loops to visualize their iterative control flow.",
      };
    }
    if (rawMsg.includes("Yield") || rawMsg.toLowerCase().includes("yield")) {
      return {
        category: "Unsupported Python Feature",
        featureName: "Generator (yield)",
        message: "Generator yield statements are not currently supported by FlowBridge.",
        fileName,
        line,
        severity: "error",
      };
    }
    if (rawMsg.includes("With") || rawMsg.toLowerCase().includes("with")) {
      return {
        category: "Unsupported Python Feature",
        featureName: "Context Manager (with)",
        message: "Context manager statements (with / async with) are not currently supported by FlowBridge.",
        fileName,
        line,
        severity: "error",
      };
    }
    if (rawMsg.includes("Match") || rawMsg.toLowerCase().includes("match")) {
      return {
        category: "Unsupported Python Feature",
        featureName: "Pattern Matching",
        message: "Python pattern matching (match/case) is not currently supported by FlowBridge.",
        fileName,
        line,
        severity: "error",
      };
    }
    return {
      category: "Unsupported Python Feature",
      featureName: "Unsupported Syntax",
      message: rawMsg,
      fileName,
      line,
      severity: "error",
    };
  }

  if (code === "SYNTAX_ERROR" || rawMsg.toLowerCase().includes("syntaxerror") || rawMsg.toLowerCase().includes("invalid syntax")) {
    return {
      category: "Syntax Error",
      featureName: "Invalid Python Syntax",
      message: rawMsg || "The Python file contains invalid syntax and could not be parsed.",
      fileName,
      line,
      severity: "error",
      tip: "Check the source code at the indicated line for syntax errors.",
    };
  }

  if (code === "RESOLUTION_FAILED" || code === "UNRESOLVED_CALL" || diag.severity === "warning") {
    return {
      category: "Resolution Warning",
      featureName: "Import / Call Resolution Warning",
      message: rawMsg,
      fileName,
      line,
      severity: "warning",
    };
  }

  return {
    category: "Analysis Error",
    featureName: code || "Analysis Error",
    message: rawMsg,
    fileName,
    line,
    severity: diag.severity,
  };
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
  const renderRequest = useRef<AbortController | null>(null);
  useEffect(() => () => renderRequest.current?.abort(), []);
  const [panel, setPanel] = useState<'settings' | 'workspace' | null>(null);
  const [hideComments, setHideComments] = useState(false);
  const [commentRanges, setCommentRanges] = useState<Record<string, SourceLocation[]>>({});
  const [displayError, setDisplayError] = useState<string | null>(null);
  useEffect(() => {
    if (!hideComments || !project) return;
    const request = new AbortController();
    setDisplayError(null);
    axios.get<{projectId: string; files: Record<string, SourceLocation[]>}>(
      `${API_BASE_URL}/api/projects/${project.projectID}/display`,
      {signal: request.signal, timeout: REQUEST_TIMEOUT_MS},
    ).then(({data}) => {
      if (!request.signal.aborted && data.projectId === project.projectID) setCommentRanges(data.files);
    }).catch(error => {
      if (!request.signal.aborted) {
        setDisplayError(requestError(error));
        setHideComments(false);
      }
    });
    return () => request.abort();
  }, [hideComments, project]);

  // Modals state
  const [isUploadModalOpen, setIsUploadModalOpen] = useState<boolean>(false);
  const [isExportModalOpen, setIsExportModalOpen] = useState<boolean>(false);

  // File statuses lookup
  const fileStatuses = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    if (!renderData) return map;

    // Check analysisFiles
    if (renderData.analysisFiles) {
      for (const f of renderData.analysisFiles) {
        if (f.fileId) map[f.fileId] = f.status;
        if (f.fileName) map[f.fileName] = f.status;
      }
    }
    // Check flowchart.files
    if (renderData.flowchart?.files) {
      for (const f of renderData.flowchart.files) {
        if (f.fileId && f.status) map[f.fileId] = f.status;
        if (f.fileName && f.status) map[f.fileName] = f.status;
      }
    }
    return map;
  }, [renderData]);

  // Diagnostics for active file
  const activeFileDiagnostics = useMemo<ClassifiedDiagnostic[]>(() => {
    if (!renderData || !renderData.diagnostics || !activeFile) return [];
    const fid = getFileId(activeFile);
    const fname = getFileName(activeFile);

    return renderData.diagnostics
      .filter((d) => d.fileId === fid || (d.sourceLocation && d.sourceLocation.fileId === fid))
      .map((d) => classifyDiagnostic(d, fname));
  }, [renderData, activeFile]);

  const activeFileStatus = useMemo<string>(() => {
    if (!activeFile) return "complete";
    const fid = getFileId(activeFile);
    const fname = getFileName(activeFile);
    return fileStatuses[fid] || fileStatuses[fname] || (activeFileDiagnostics.some(d => d.severity === "error") ? "unsupported" : "complete");
  }, [activeFile, fileStatuses, activeFileDiagnostics]);

  // 1. Handle Project Uploaded from UploadModal
  function handleProjectLoaded(uploadedProject: PyProject) {
    renderRequest.current?.abort();
    renderRequest.current = null;
    setIsLoading(false);
    setProject(uploadedProject);
    setCommentRanges({});
    setRenderData(null);
    setActiveGraphId(null);
    setBreadcrumbs([]);
    setErrorMessage(null);
    setHighlightedLines(null);
    setHighlightedNodeId(null);
    setActiveFunction(null);

    // Display the overall project view page rather than opening the first file
    setActiveFile(null);
    setActiveFunction(null);
  }

  // 2. Handle Generate Flowchart via StartButton
  async function handleStartGeneration() {
    if (!project) return;

    const projectId = project.projectID || project.id;
    if (!projectId) {
      setErrorMessage("No project ID found. Please upload the project again.");
      return;
    }

    renderRequest.current?.abort();
    const request = new AbortController();
    renderRequest.current = request;
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const response = await axios.post<RenderResponse>(
        `${API_BASE_URL}/api/projects/${projectId}/render`,
        undefined,
        { signal: request.signal, timeout: REQUEST_TIMEOUT_MS }
      );

      const data = response.data;
      if (request.signal.aborted || renderRequest.current !== request) return;
      if (data.projectId !== projectId || data.revisionId !== 1) {
        throw new Error("The diagram response does not match this project.");
      }
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
      if (request.signal.aborted || renderRequest.current !== request) return;
      console.error("Failed to generate diagrams:", err);
      setErrorMessage(requestError(err));
    } finally {
      if (renderRequest.current === request) {
        renderRequest.current = null;
        setIsLoading(false);
      }
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
    setHighlightedLines(null);

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
    setHighlightedNodeId(null);

    // Check source mapping index for this line
    const fileIndex = renderData.sourceMapping?.files?.[fileId];
    const candidateNodes = fileIndex?.lineToNodes?.[String(lineNumber)];

    if (candidateNodes && candidateNodes.length > 0) {
      // Prioritize nodes present in the current active graph
      const activeNodes = candidateNodes.filter(
        (nid) => renderData.sourceMapping?.nodes?.[nid]?.graphId === activeGraphId
      );
      activeNodes.sort((left, right) => {
        const a = renderData.sourceMapping!.nodes[left].span!;
        const b = renderData.sourceMapping!.nodes[right].span!;
        return (a.endLine - a.startLine) - (b.endLine - b.startLine)
          || (a.endColumn - a.startColumn) - (b.endColumn - b.startColumn);
      });
      if (activeNodes.length) setHighlightedNodeId(activeNodes[0]);
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

      const file = targetFileId
        ? project.files.find((f) => getFileId(f) === targetFileId)
        : project.files.find((f) => f.filePath === label);
      if (file) {
        setActiveFile(file);

        // If file has error diagnostics, auto-highlight the problematic line in the editor
        const fId = getFileId(file);
        const diags = (renderData.diagnostics || []).filter(
          (d) => d.fileId === fId || d.sourceLocation?.fileId === fId
        );
        const firstErr = diags.find((d) => d.severity === "error" && d.sourceLocation?.startLine);
        if (firstErr && firstErr.sourceLocation) {
          setHighlightedLines([firstErr.sourceLocation.startLine, firstErr.sourceLocation.startLine]);
        }
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
        if (f) {
          setActiveFile(f);
          const fId = getFileId(f);
          const diags = (renderData?.diagnostics || []).filter(
            (d) => d.fileId === fId || d.sourceLocation?.fileId === fId
          );
          const firstErr = diags.find((d) => d.severity === "error" && d.sourceLocation?.startLine);
          if (firstErr && firstErr.sourceLocation) {
            setHighlightedLines([firstErr.sourceLocation.startLine, firstErr.sourceLocation.startLine]);
          }
        }
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

    const fId = getFileId(file);

    // If file has error diagnostics, auto-highlight the line
    if (renderData?.diagnostics) {
      const diags = renderData.diagnostics.filter(
        (d) => d.fileId === fId || d.sourceLocation?.fileId === fId
      );
      const firstErr = diags.find((d) => d.severity === "error" && d.sourceLocation?.startLine);
      if (firstErr && firstErr.sourceLocation) {
        setHighlightedLines([firstErr.sourceLocation.startLine, firstErr.sourceLocation.startLine]);
      }
    }

    if (renderData) {
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

  // Check if viewing an unsupported or failed file
  const isViewingUnsupportedFile = Boolean(
    activeFile && (activeFileStatus === "unsupported" || activeFileStatus === "failed" || activeFileDiagnostics.some(d => d.severity === "error"))
  );

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
          <div className="user-profile">
            <button type="button" className="workspaceButton" title="Current workspace" onClick={() => setPanel('workspace')}>
              <img src="./ProfilePicture.png" alt="Local session" className="loginIcon" />
            </button>
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
              disabled={!activeSvg || isViewingUnsupportedFile}
              style={{ opacity: activeSvg ? 1 : 0.4 }}
            >
              <img src="ExportButton.png" alt="Export Icon" className="toolIcon" />
            </button>
          </div>

          <div className="toolbar-bottom">
            <button
              className="sidebarIconButton"
              title="Display settings"
              onClick={() => setPanel('settings')}
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
                ? `${activeFunction.functionName}() (Lines ${activeFunction.startLine}-${activeFunction.endLine})`
                : activeFile
                ? `${getFileName(activeFile)}`
                : project
                ? `${project.projectName || project.name}`
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
                fileStatuses={fileStatuses}
                hiddenRanges={hideComments ? commentRanges[getFileId(activeFile)] || [] : []}
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

          {/* Right Card: Flowchart Canvas or Unsupported Feature Card */}
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
              ) : isViewingUnsupportedFile ? (
                /* Dedicated Unsupported Python Feature / Diagnostic Display */
                <div
                  style={{
                    padding: "28px 32px",
                    height: "100%",
                    overflowY: "auto",
                    boxSizing: "border-box",
                    display: "flex",
                    flexDirection: "column",
                    gap: "20px",
                    backgroundColor: "#fafbfc",
                  }}
                >
                  {(() => {
                    const primaryDiag = activeFileDiagnostics[0] || {
                      category: "Unsupported Python Feature",
                      featureName: "Unsupported Syntax",
                      message: "This file contains unsupported Python constructs and cannot be rendered as a flowchart.",
                      fileName: getFileName(activeFile),
                      severity: "error",
                    };
                    const isUnsupported = primaryDiag.category === "Unsupported Python Feature";

                    return (
                      <>
                        {/* Alert Header Banner */}
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "14px",
                            padding: "16px 20px",
                            borderRadius: "8px",
                            backgroundColor: isUnsupported ? "#fff8e1" : "#ffebee",
                            border: `1px solid ${isUnsupported ? "#ffb74d" : "#ef5350"}`,
                            color: isUnsupported ? "#b78103" : "#c62828",
                          }}
                        >
                          <span style={{ fontSize: "28px" }}>{isUnsupported ? "⚠" : "✕"}</span>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: "17px" }}>{primaryDiag.category}</div>
                            <div style={{ fontSize: "13px", opacity: 0.95, marginTop: "2px" }}>
                              {isUnsupported
                                ? "This file contains Python syntax or language constructs outside FlowBridge's supported subset."
                                : "An error occurred while parsing and analyzing this Python file."}
                            </div>
                          </div>
                        </div>

                        {/* Structured Error Details Card */}
                        <div
                          style={{
                            backgroundColor: "#ffffff",
                            border: "1px solid #dee2e6",
                            borderRadius: "8px",
                            padding: "22px 24px",
                            boxShadow: "0 2px 6px rgba(0,0,0,0.04)",
                            display: "flex",
                            flexDirection: "column",
                            gap: "14px",
                          }}
                        >
                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "110px 1fr",
                              rowGap: "12px",
                              fontSize: "14px",
                              alignItems: "center",
                            }}
                          >
                            <span style={{ fontWeight: 600, color: "#6c757d" }}>File:</span>
                            <span style={{ fontFamily: "monospace", color: "#1a73e8", fontWeight: 600 }}>
                              {primaryDiag.fileName}
                            </span>

                            {primaryDiag.line !== undefined && (
                              <>
                                <span style={{ fontWeight: 600, color: "#6c757d" }}>Line:</span>
                                <span style={{ display: "inline-flex", alignItems: "center", gap: "10px" }}>
                                  <span style={{ fontWeight: 700, color: "#d97706" }}>Line {primaryDiag.line}</span>
                                  <button
                                    onClick={() => {
                                      if (primaryDiag.line) {
                                        setHighlightedLines([primaryDiag.line, primaryDiag.line]);
                                      }
                                    }}
                                    style={{
                                      background: "#f0f7ff",
                                      border: "1px solid #c8e1ff",
                                      borderRadius: "4px",
                                      padding: "3px 10px",
                                      fontSize: "12px",
                                      color: "#0366d6",
                                      cursor: "pointer",
                                      fontWeight: 600,
                                    }}
                                  >
                                    Highlight in Editor
                                  </button>
                                </span>
                              </>
                            )}

                            <span style={{ fontWeight: 600, color: "#6c757d" }}>Feature:</span>
                            <span style={{ fontWeight: 600, color: "#212529" }}>{primaryDiag.featureName}</span>

                            <span style={{ fontWeight: 600, color: "#6c757d" }}>Message:</span>
                            <span style={{ color: "#212529", lineHeight: 1.5 }}>"{primaryDiag.message}"</span>
                          </div>

                          {primaryDiag.tip && (
                            <div
                              style={{
                                marginTop: "8px",
                                padding: "12px 16px",
                                backgroundColor: "#f8f9fa",
                                borderRadius: "6px",
                                borderLeft: "4px solid #1a73e8",
                                fontSize: "13px",
                                color: "#495057",
                                lineHeight: 1.5,
                              }}
                            >
                              <strong style={{ color: "#1a73e8" }}>Recommendation: </strong>
                              {primaryDiag.tip}
                            </div>
                          )}
                        </div>

                        {/* Navigation Actions */}
                        <div style={{ display: "flex", gap: "12px" }}>
                          <button
                            onClick={() => {
                              setActiveFile(null);
                              setActiveFunction(null);
                              setHighlightedLines(null);
                              setHighlightedNodeId(null);
                              if (renderData) {
                                setActiveGraphId(renderData.projectGraphId);
                                setBreadcrumbs([{ id: renderData.projectGraphId, label: "Project View", type: "project" }]);
                              }
                            }}
                            style={{
                              padding: "9px 18px",
                              backgroundColor: "#ffffff",
                              border: "1px solid #ced4da",
                              borderRadius: "6px",
                              cursor: "pointer",
                              fontSize: "13px",
                              fontWeight: 600,
                              color: "#495057",
                              transition: "all 0.15s ease",
                            }}
                            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#1a73e8")}
                            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#ced4da")}
                          >
                            ← Return to Project View
                          </button>
                        </div>
                      </>
                    );
                  })()}
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
      <WorkspaceDialog panel={panel} project={project} hideComments={hideComments} error={displayError}
        onHideComments={setHideComments} onClose={() => setPanel(null)} />
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
