import React, { useEffect, useLayoutEffect, useRef, useState, useCallback } from "react";

interface FlowchartCanvasProps {
  svgContent?: string | null;
  isLoading?: boolean;
  onNodeClick?: (nodeId: string) => void;
  title?: string;
  highlightedNodeId?: string | null;
  viewType?: "project" | "file" | "function" | "module";
}

export default function FlowchartCanvas({
  svgContent,
  isLoading = false,
  onNodeClick,
  title,
  highlightedNodeId,
  viewType = "project",
}: FlowchartCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const contentWrapperRef = useRef<HTMLDivElement>(null);
  const prevSvgRef = useRef<string | null | undefined>(undefined);

  // Zoom and Pan states
  const [zoomLevel, setZoomLevel] = useState<number>(1);
  const [panOffset, setPanOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Intelligent Fit to View Calculation
  const handleFitToView = useCallback(() => {
    if (!containerRef.current || !contentWrapperRef.current) return;
    const svgEl = contentWrapperRef.current.querySelector("svg");
    if (!svgEl) return;

    // Read viewBox or fallback client size
    const viewBox = svgEl.viewBox?.baseVal;
    let svgWidth = viewBox && viewBox.width > 0 ? viewBox.width : svgEl.clientWidth;
    let svgHeight = viewBox && viewBox.height > 0 ? viewBox.height : svgEl.clientHeight;

    if (!svgWidth || svgWidth <= 0) svgWidth = 800;
    if (!svgHeight || svgHeight <= 0) svgHeight = 600;

    const cWidth = containerRef.current.clientWidth;
    const cHeight = containerRef.current.clientHeight;

    const paddingX = 40;
    const paddingY = 40;
    const availWidth = Math.max(100, cWidth - paddingX);
    const availHeight = Math.max(100, cHeight - paddingY);

    const scaleX = availWidth / svgWidth;
    const scaleY = availHeight / svgHeight;

    let targetScale = 1.0;
    let targetPanX = 0;
    let targetPanY = 20;

    const isTallVerticalDiagram = svgHeight > 1.8 * svgWidth || viewType === "file";

    if (isTallVerticalDiagram) {
      // Scenario A: Tall linear CFG (File View)
      // Fit to container width so nodes & labels remain comfortable to read, top-aligned.
      targetScale = Math.max(0.65, Math.min(scaleX, 1.15));
      targetPanX = (cWidth - svgWidth * targetScale) / 2;
      targetPanY = 20;
    } else if (viewType === "project") {
      // Scenario B: Project Overall View
      // Prevent excessive zooming out: floor at 0.55 so text stays readable!
      const rawFit = Math.min(scaleX, scaleY);
      targetScale = Math.max(0.55, Math.min(rawFit, 1.25));
      targetPanX = (cWidth - svgWidth * targetScale) / 2;
      targetPanY = Math.max(20, (cHeight - svgHeight * targetScale) / 2);
    } else {
      // Scenario C: Function View (compact CFG)
      // Fit within bounds, floor at 0.65, center both X and Y
      const rawFit = Math.min(scaleX, scaleY);
      targetScale = Math.max(0.65, Math.min(rawFit, 1.3));
      targetPanX = (cWidth - svgWidth * targetScale) / 2;
      targetPanY = Math.max(20, (cHeight - svgHeight * targetScale) / 2);
    }

    setZoomLevel(targetScale);
    setPanOffset({ x: targetPanX, y: targetPanY });
  }, [viewType]);

  // Fit before painting so the diagram cannot move during the first node click.
  useLayoutEffect(() => {
    if (prevSvgRef.current === svgContent) {
      return;
    }
    prevSvgRef.current = svgContent;

    handleFitToView();
  }, [svgContent, handleFitToView]);

  // Mouse wheel zoom (centered around current viewport, no jumping)
  function handleWheel(e: React.WheelEvent<HTMLDivElement>) {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    setZoomLevel((prev) => Math.min(Math.max(prev * zoomFactor, 0.25), 4.0));
  }

  // Mouse pan handlers
  function handleMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    const target = e.target as HTMLElement;
    // Don't drag if clicking a clickable node
    if (target.closest(".clickable")) return;

    setIsDragging(true);
    setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
  }

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!isDragging) return;
    setPanOffset({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  }

  function handleMouseUp() {
    setIsDragging(false);
  }

  // Attach click listeners to nodes in SVG
  useEffect(() => {
    if (!contentWrapperRef.current || !svgContent) return;

    const container = contentWrapperRef.current;
    const clickableElements = container.querySelectorAll("g[id]");

    function handleClick(this: SVGGraphicsElement, ev: Event) {
      ev.stopPropagation();
      const nodeId = this.id;
      if (nodeId && onNodeClick) {
        onNodeClick(nodeId);
      }
    }

    clickableElements.forEach((el) => {
      el.addEventListener("click", handleClick as EventListener);
    });

    return () => {
      clickableElements.forEach((el) => {
        el.removeEventListener("click", handleClick as EventListener);
      });
    };
  }, [svgContent, onNodeClick]);

  // Visual highlight for selected node WITHOUT moving the flowchart viewport
  useEffect(() => {
    if (!contentWrapperRef.current || !svgContent) return;

    const container = contentWrapperRef.current;

    // Reset previous highlights
    container.querySelectorAll(".node-highlighted").forEach((el) => {
      el.classList.remove("node-highlighted");
      const shape = el.querySelector("rect, polygon");
      if (shape) {
        shape.removeAttribute("style");
      }
    });

    if (!highlightedNodeId) return;

    // Highlight target node in-place: NO auto-panning, NO viewport jump
    const targetNode = container.querySelector(`g[id="${highlightedNodeId}"]`);
    if (targetNode) {
      targetNode.classList.add("node-highlighted");
      const shape = targetNode.querySelector("rect, polygon");
      if (shape) {
        shape.setAttribute(
          "style",
          "stroke: #ff9800 !important; stroke-width: 3.5px !important; filter: drop-shadow(0 0 8px rgba(255, 152, 0, 0.85)) !important;"
        );
      }
    }
  }, [highlightedNodeId, svgContent]);

  if (isLoading) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          gap: "16px",
          color: "#1a73e8",
        }}
      >
        <div
          style={{
            width: "48px",
            height: "48px",
            border: "4px solid #e3f2fd",
            borderTop: "4px solid #1a73e8",
            borderRadius: "50%",
            animation: "spin 1s linear infinite",
          }}
        />
        <span style={{ fontWeight: 600, fontSize: "15px" }}>Analyzing project & generating flowchart...</span>
      </div>
    );
  }

  // If no SVG yet, show clean placeholder message
  if (!svgContent) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          padding: "32px",
          color: "#8c959f",
          textAlign: "center",
          backgroundColor: "#ffffff",
        }}
      >

        <p style={{ margin: "0 0 8px 0", fontWeight: 600, color: "#343a40", fontSize: "16px" }}>
          No Flowchart Generated Yet
        </p>
        <p style={{ margin: 0, fontSize: "13px", color: "#6c757d", maxWidth: "340px", lineHeight: "1.5" }}>
          Click the <strong style={{ color: "#1a73e8" }}>Start</strong> button in the top navigation bar to analyze the project and render control-flow diagrams.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        overflow: "hidden",
        cursor: isDragging ? "grabbing" : "grab",
        userSelect: "none",
        backgroundColor: "#ffffff",
      }}
    >
      {/* Floating Toolbar Controls */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          right: "12px",
          zIndex: 20,
          display: "flex",
          gap: "6px",
          backgroundColor: "rgba(255, 255, 255, 0.95)",
          padding: "5px 8px",
          borderRadius: "8px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
          border: "1px solid #dee2e6",
        }}
      >
        <button
          onClick={() => setZoomLevel((z) => Math.min(z + 0.15, 4.0))}
          title="Zoom In"
          style={{
            border: "1px solid #ced4da",
            background: "#ffffff",
            borderRadius: "4px",
            width: "30px",
            height: "28px",
            cursor: "pointer",
            fontWeight: "bold",
            fontSize: "14px",
            color: "#333",
          }}
        >
          +
        </button>
        <button
          onClick={() => setZoomLevel((z) => Math.max(z - 0.15, 0.25))}
          title="Zoom Out"
          style={{
            border: "1px solid #ced4da",
            background: "#ffffff",
            borderRadius: "4px",
            width: "30px",
            height: "28px",
            cursor: "pointer",
            fontWeight: "bold",
            fontSize: "14px",
            color: "#333",
          }}
        >
          -
        </button>
        <button
          onClick={handleFitToView}
          title="Fit to View"
          style={{
            border: "1px solid #ced4da",
            background: "#ffffff",
            borderRadius: "4px",
            padding: "0 10px",
            height: "28px",
            cursor: "pointer",
            fontSize: "12px",
            fontWeight: 600,
            color: "#1a73e8",
          }}
        >
          ⛶ Fit
        </button>
        <button
          onClick={() => {
            setZoomLevel(1);
            if (containerRef.current && contentWrapperRef.current) {
              const svgEl = contentWrapperRef.current.querySelector("svg");
              const viewBox = svgEl?.viewBox?.baseVal;
              const w = (viewBox && viewBox.width > 0 ? viewBox.width : svgEl?.clientWidth) || 800;
              const cW = containerRef.current.clientWidth;
              setPanOffset({ x: (cW - w) / 2, y: 20 });
            } else {
              setPanOffset({ x: 0, y: 20 });
            }
          }}
          title="Reset View (100%)"
          style={{
            border: "1px solid #ced4da",
            background: "#ffffff",
            borderRadius: "4px",
            padding: "0 8px",
            height: "28px",
            cursor: "pointer",
            fontSize: "11px",
            fontWeight: 600,
            color: "#495057",
          }}
        >
          Reset ({Math.round(zoomLevel * 100)}%)
        </button>
      </div>

      {/* SVG Canvas with Clean Absolute Transform Origin */}
      <div
        ref={contentWrapperRef}
        style={{
          display: "inline-block",
          transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomLevel})`,
          transformOrigin: "top left",
          transition: isDragging ? "none" : "transform 0.1s ease-out",
        }}
        dangerouslySetInnerHTML={{ __html: svgContent }}
      />
    </div>
  );
}
