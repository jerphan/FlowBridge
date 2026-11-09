import React, { useEffect, useRef, useState, useCallback } from "react";
import { FunctionInfo, SourceFile, SourceLocation } from "../types/flowchart";
import {filterSourceLine} from "../sourceDisplay";

interface SourceCodeViewerProps {
  activeFile?: SourceFile | null;
  activeFunction?: FunctionInfo | null;
  highlightedLines?: [number, number] | null;
  allFiles?: SourceFile[];
  onSelectFile?: (file: SourceFile) => void;
  onLineClick?: (lineNumber: number, fileId: string) => void;
  onBackToProjectFiles?: () => void;
  fileStatuses?: Record<string, string>;
  hiddenRanges?: SourceLocation[];
}

function getFileId(f?: SourceFile | null, fallbackIdx = 0): string {
  if (!f) return `file-${fallbackIdx}`;
  return f.fileID || f.fileId || `file-${fallbackIdx}`;
}

function getFileName(f?: SourceFile | null, fallbackIdx = 0): string {
  if (!f) return `file-${fallbackIdx}.py`;
  return f.filePath || f.path || f.fileName || `file-${fallbackIdx}.py`;
}

export default function SourceCodeViewer({
  activeFile,
  activeFunction,
  highlightedLines,
  allFiles = [],
  onSelectFile,
  onLineClick,
  onBackToProjectFiles,
  fileStatuses = {},
  hiddenRanges = [],
}: SourceCodeViewerProps) {
  const lineRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const codeContainerRef = useRef<HTMLDivElement>(null);
  const filesContainerRef = useRef<HTMLDivElement>(null);

  // Scroll tracking states for interactive indicators and buttons
  const [canScrollDownFiles, setCanScrollDownFiles] = useState<boolean>(false);
  const [canScrollUpFiles, setCanScrollUpFiles] = useState<boolean>(false);
  const [canScrollDownCode, setCanScrollDownCode] = useState<boolean>(false);
  const [canScrollUpCode, setCanScrollUpCode] = useState<boolean>(false);

  // Check scroll bounds for Project Files container
  const checkFilesScroll = useCallback(() => {
    const el = filesContainerRef.current;
    if (!el) return;
    const hasMoreBelow = el.scrollTop < el.scrollHeight - el.clientHeight - 15;
    const hasMoreAbove = el.scrollTop > 15;
    setCanScrollDownFiles(hasMoreBelow);
    setCanScrollUpFiles(hasMoreAbove);
  }, []);

  // Check scroll bounds for Code container
  const checkCodeScroll = useCallback(() => {
    const el = codeContainerRef.current;
    if (!el) return;
    const hasMoreBelow = el.scrollTop < el.scrollHeight - el.clientHeight - 20;
    const hasMoreAbove = el.scrollTop > 20;
    setCanScrollDownCode(hasMoreBelow);
    setCanScrollUpCode(hasMoreAbove);
  }, []);

  // Smooth scroll helper actions
  function handleScrollDown(ref: React.RefObject<HTMLDivElement | null>) {
    if (!ref.current) return;
    ref.current.scrollBy({ top: 320, behavior: "smooth" });
  }

  function handleScrollUp(ref: React.RefObject<HTMLDivElement | null>) {
    if (!ref.current) return;
    ref.current.scrollBy({ top: -320, behavior: "smooth" });
  }

  function handleScrollToBottom(ref: React.RefObject<HTMLDivElement | null>) {
    if (!ref.current) return;
    ref.current.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }

  function handleScrollToTop(ref: React.RefObject<HTMLDivElement | null>) {
    if (!ref.current) return;
    ref.current.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Update scroll bounds check whenever data changes
  useEffect(() => {
    const timer = setTimeout(() => {
      checkFilesScroll();
      checkCodeScroll();
    }, 100);
    return () => clearTimeout(timer);
  }, [allFiles, activeFile, activeFunction, checkFilesScroll, checkCodeScroll]);

  // Auto-scroll to highlighted line within the local codeContainerRef ONLY
  useEffect(() => {
    if (!highlightedLines || !highlightedLines[0] || !codeContainerRef.current) return;

    const startLine = highlightedLines[0];
    const targetEl = lineRefs.current[startLine];
    if (!targetEl) return;

    const container = codeContainerRef.current;
    const targetOffsetTop = targetEl.offsetTop;
    const containerHeight = container.clientHeight;

    const scrollTarget = Math.max(0, targetOffsetTop - containerHeight / 3);
    container.scrollTo({ top: scrollTarget, behavior: "smooth" });
  }, [highlightedLines]);

  // Case 1: No project loaded yet -> show empty placeholder state
  if (!activeFile && allFiles.length === 0) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          padding: "24px",
          color: "#8c959f",
          textAlign: "center",
        }}
      >

        <p style={{ margin: "0 0 6px 0", fontWeight: 600, color: "#495057", fontSize: "14px" }}>
          No Python source file loaded
        </p>
        <p style={{ margin: 0, fontSize: "12px", color: "#6c757d", maxWidth: "260px" }}>
          Upload a file, ZIP project, or import a GitHub repository using the left toolbar.
        </p>
      </div>
    );
  }

  // Case 2: In Project View (no single file selected) -> display all project files list
  if (!activeFile && allFiles.length > 0) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          width: "100%",
          height: "100%",
          overflow: "hidden",
          backgroundColor: "#ffffff",
          position: "relative",
        }}
      >
        {/* Header Bar with quick scroll controls */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "10px 16px",
            backgroundColor: "#f8f9fa",
            borderBottom: "1px solid #dee2e6",
            fontSize: "13px",
            fontWeight: 600,
            color: "#343a40",
            flexShrink: 0,
          }}
        >
          <span>Project Files ({allFiles.length})</span>
          <div style={{ display: "flex", gap: "6px" }}>
            <button
              onClick={() => handleScrollUp(filesContainerRef)}
              disabled={!canScrollUpFiles}
              className="scrollNavBtn"
              title="Scroll Up"
              style={{ opacity: canScrollUpFiles ? 1 : 0.4 }}
            >
              ▲ Up
            </button>
            <button
              onClick={() => handleScrollDown(filesContainerRef)}
              disabled={!canScrollDownFiles}
              className="scrollNavBtn"
              title="Scroll Down"
              style={{ opacity: canScrollDownFiles ? 1 : 0.4 }}
            >
              ▼ Down
            </button>
          </div>
        </div>

        {/* Scrollable list of files line-by-line */}
        <div
          ref={filesContainerRef}
          onScroll={checkFilesScroll}
          className="sourceCodeScrollArea"
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "8px",
            flex: 1,
            width: "100%",
            height: "100%",
            overflowY: "auto",
            overflowX: "hidden",
            padding: "14px 16px 40px 16px",
            boxSizing: "border-box",
            backgroundColor: "#ffffff",
          }}
        >
          <p style={{ fontSize: "13px", color: "#555", margin: "0 0 6px 0", flexShrink: 0 }}>
            Click any file below or in the Project View flowchart on the right to inspect its execution flow:
          </p>

          {allFiles.map((f, i) => {
            const fId = getFileId(f, i);
            const fName = getFileName(f, i);
            const fContent = f.fileContent || f.content || "";
            const fStatus = fileStatuses[fId] || fileStatuses[fName];

            return (
              <div
                key={fId}
                onClick={() => onSelectFile && onSelectFile(f)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "12px 16px",
                  backgroundColor: "#f8f9fa",
                  borderRadius: "8px",
                  border: "1px solid #dee2e6",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  flexShrink: 0,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "#1a73e8";
                  e.currentTarget.style.backgroundColor = "#f0f7ff";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "#dee2e6";
                  e.currentTarget.style.backgroundColor = "#f8f9fa";
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>

                  <span style={{ fontWeight: 600, fontSize: "14px", color: "#212529" }}>{fName}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  {fStatus === "unsupported" && (
                    <span style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "10px", backgroundColor: "#fff3e0", color: "#e65100", fontWeight: 600 }}>
                      ⚠ Unsupported
                    </span>
                  )}
                  {fStatus === "failed" && (
                    <span style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "10px", backgroundColor: "#ffebee", color: "#c62828", fontWeight: 600 }}>
                      ✕ Failed
                    </span>
                  )}
                  {fStatus === "complete" && (
                    <span style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "10px", backgroundColor: "#e8f5e9", color: "#2e7d32", fontWeight: 600 }}>
                      ✓ Ready
                    </span>
                  )}
                  <span style={{ fontSize: "12px", color: "#6c757d" }}>
                    {f.byteSize || fContent.length} bytes
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Floating Scroll Down button when more files are below */}
        {canScrollDownFiles && (
          <button
            onClick={() => handleScrollDown(filesContainerRef)}
            className="floatingScrollBtn"
            title="Scroll down to see more files"
          >
            <span>▼</span> Scroll Down
          </button>
        )}
      </div>
    );
  }

  // Case 3: Viewing a specific File or Function -> White background source code viewer
  const activeFId = getFileId(activeFile);
  const activeFName = getFileName(activeFile);
  const rawContent = activeFile?.fileContent || activeFile?.content || "";
  const rawLines = rawContent.split("\n");

  // Determine line slice
  let startIdx = 0;
  let endIdx = rawLines.length;

  if (activeFunction) {
    startIdx = Math.max(0, activeFunction.startLine - 1);
    endIdx = Math.min(rawLines.length, activeFunction.endLine);
  }

  const displayedLines = rawLines.slice(startIdx, endIdx);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        backgroundColor: "#ffffff",
        position: "relative",
      }}
    >
      {/* File Navigation & Scroll Controls Bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 14px",
          backgroundColor: "#f8f9fa",
          borderBottom: "1px solid #e1e4e8",
          fontSize: "12px",
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {allFiles.length > 1 && onBackToProjectFiles && (
            <button
              onClick={onBackToProjectFiles}
              title="View all project files"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
                background: "none",
                border: "1px solid #ced4da",
                borderRadius: "5px",
                padding: "3px 8px",
                cursor: "pointer",
                fontSize: "12px",
                color: "#1a73e8",
                fontWeight: 600,
              }}
            >
              ← All Files ({allFiles.length})
            </button>
          )}
          <span style={{ color: "#343a40", fontSize: "12px", fontWeight: 600 }}>
            {activeFunction ? `${activeFunction.functionName}()` : `${activeFName}`}
          </span>
          <span style={{ color: "#6c757d", fontSize: "11px" }}>
            ({displayedLines.length} lines)
          </span>
        </div>

        {/* Scroll Controls: Up, Down, Bottom */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <button
            onClick={() => handleScrollUp(codeContainerRef)}
            title="Scroll Up"
            className="scrollNavBtn"
            disabled={!canScrollUpCode}
            style={{ opacity: canScrollUpCode ? 1 : 0.4 }}
          >
            ▲ Up
          </button>
          <button
            onClick={() => handleScrollDown(codeContainerRef)}
            title="Scroll Down"
            className="scrollNavBtn"
          >
            ▼ Down
          </button>
          <button
            onClick={() => handleScrollToBottom(codeContainerRef)}
            title="Scroll to Bottom"
            className="scrollNavBtn"
          >
            ⤓ Bottom
          </button>
        </div>
      </div>

      {/* Code Text Area with Dedicated Vertical & Horizontal Scroll */}
      <div
        ref={codeContainerRef}
        onScroll={checkCodeScroll}
        className="sourceCodeScrollArea"
        style={{
          flex: 1,
          width: "100%",
          height: "100%",
          overflowX: "auto",
          overflowY: "auto",
          backgroundColor: "#ffffff",
          color: "#24292f",
          fontFamily: 'Consolas, "Fira Code", "Courier New", monospace',
          fontSize: "13px",
          lineHeight: "1.65",
          padding: "12px 0 40px 0",
          boxSizing: "border-box",
        }}
      >
        <div style={{ minWidth: "max-content", width: "100%" }}>
          {displayedLines.map((lineText, idx) => {
            const actualLineNum = startIdx + idx + 1;
            const displayedText = filterSourceLine(lineText, actualLineNum, hiddenRanges);
            if (displayedText === null) return null;
            const isHighlighted =
              highlightedLines &&
              actualLineNum >= highlightedLines[0] &&
              actualLineNum <= highlightedLines[1];

            return (
              <div
                key={actualLineNum}
                ref={(el) => {
                  lineRefs.current[actualLineNum] = el;
                }}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  backgroundColor: isHighlighted ? "rgba(255, 235, 59, 0.35)" : "transparent",
                  borderLeft: isHighlighted ? "4px solid #f57f17" : "4px solid transparent",
                  padding: "0 12px",
                }}
              >
                {/* Clickable Line Number */}
                <span
                  onClick={() => onLineClick && onLineClick(actualLineNum, activeFId)}
                  title={`Line ${actualLineNum}: Click to highlight in flowchart`}
                  style={{
                    width: "48px",
                    minWidth: "48px",
                    textAlign: "right",
                    paddingRight: "16px",
                    color: isHighlighted ? "#d97706" : "#8c959f",
                    userSelect: "none",
                    fontWeight: isHighlighted ? 700 : 400,
                    cursor: "pointer",
                    transition: "color 0.15s ease",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = "#1a73e8")}
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.color = isHighlighted ? "#d97706" : "#8c959f")
                  }
                >
                  {actualLineNum}
                </span>

                {/* Code Text */}
                <span
                  style={{
                    whiteSpace: "pre",
                    color: isHighlighted ? "#000000" : "#24292f",
                    fontWeight: isHighlighted ? 600 : 400,
                  }}
                >
                  {displayedText || " "}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Floating Scroll Down Pill when lines extend below */}
      {canScrollDownCode && (
        <button
          onClick={() => handleScrollDown(codeContainerRef)}
          className="floatingScrollBtn"
          title="Scroll down through code"
        >
          <span>▼</span> Scroll Down
        </button>
      )}
    </div>
  );
}
