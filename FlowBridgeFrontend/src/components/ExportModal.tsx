import React from "react";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  svgContent?: string | null;
  diagramTitle?: string;
}

export default function ExportModal({
  isOpen,
  onClose,
  svgContent,
  diagramTitle = "flowchart",
}: ExportModalProps) {
  if (!isOpen) return null;

  const safeTitle = diagramTitle.toLowerCase().replace(/[^a-z0-9]+/g, "_");

  // 1. Export as SVG
  function handleExportSvg() {
    if (!svgContent) return;
    const blob = new Blob([svgContent], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${safeTitle}.svg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    onClose();
  }

  // 2. Export as High-Res PNG
  function handleExportPng() {
    if (!svgContent) return;

    const blob = new Blob([svgContent], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const img = new Image();

    img.onload = () => {
      const parser = new DOMParser();
      const doc = parser.parseFromString(svgContent, "image/svg+xml");
      const svgEl = doc.querySelector("svg");
      const viewBox = svgEl?.viewBox?.baseVal;
      const width = (viewBox && viewBox.width > 0 ? viewBox.width : svgEl?.clientWidth) || 1200;
      const height = (viewBox && viewBox.height > 0 ? viewBox.height : svgEl?.clientHeight) || 800;

      const scaleFactor = 2; // 2x resolution
      const canvas = document.createElement("canvas");
      canvas.width = width * scaleFactor;
      canvas.height = height * scaleFactor;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Draw white background
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      canvas.toBlob((pngBlob) => {
        if (!pngBlob) return;
        const pngUrl = URL.createObjectURL(pngBlob);
        const link = document.createElement("a");
        link.href = pngUrl;
        link.download = `${safeTitle}.png`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(pngUrl);
        URL.revokeObjectURL(url);
        onClose();
      }, "image/png");
    };

    img.src = url;
  }

  // 3. Export as PDF
  function handleExportPdf() {
    if (!svgContent) return;

    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      alert("Please allow popups to export diagram as PDF.");
      return;
    }

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>${diagramTitle} — FlowBridge</title>
          <style>
            @page {
              size: landscape;
              margin: 10mm;
            }
            body {
              margin: 0;
              padding: 0;
              display: flex;
              flex-direction: column;
              align-items: center;
              justify-content: center;
              min-height: 100vh;
              background-color: #ffffff;
              font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            }
            .header-banner {
              text-align: center;
              margin-bottom: 20px;
              color: #1a73e8;
              font-size: 20px;
              font-weight: bold;
            }
            .svg-wrap {
              width: 100%;
              max-width: 95vw;
              display: flex;
              justify-content: center;
            }
            svg {
              max-width: 100%;
              height: auto;
            }
          </style>
        </head>
        <body>
          <div class="header-banner">${diagramTitle}</div>
          <div class="svg-wrap">${svgContent}</div>
          <script>
            window.onload = function() {
              setTimeout(function() {
                window.print();
              }, 400);
            };
          </script>
        </body>
      </html>
    `);
    printWindow.document.close();
    onClose();
  }

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.5)",
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        animation: "fadeIn 0.2s ease-out",
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: "#ffffff",
          borderRadius: "14px",
          width: "460px",
          maxWidth: "92vw",
          boxShadow: "0 10px 30px rgba(0,0,0,0.25)",
          overflow: "hidden",
          border: "1px solid #d0d7de",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            backgroundColor: "#1a73e8",
            color: "#ffffff",
            padding: "16px 20px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div>
            <h3 style={{ margin: 0, fontSize: "17px", fontWeight: 700 }}>Export Diagram</h3>
            <p style={{ margin: "3px 0 0 0", fontSize: "12px", opacity: 0.9 }}>
              Select an image or document format to export the active flowchart.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#ffffff",
              fontSize: "20px",
              cursor: "pointer",
              lineHeight: 1,
              padding: "4px 8px",
            }}
          >
            ✕
          </button>
        </div>

        {/* Options List */}
        <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "10px" }}>
          {/* SVG Option */}
          <button
            onClick={handleExportSvg}
            disabled={!svgContent}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 16px",
              border: "1px solid #ced4da",
              borderRadius: "8px",
              backgroundColor: "#ffffff",
              cursor: svgContent ? "pointer" : "not-allowed",
              opacity: svgContent ? 1 : 0.5,
              transition: "all 0.15s ease",
              textAlign: "left",
            }}
            onMouseEnter={(e) => {
              if (svgContent) {
                e.currentTarget.style.borderColor = "#1a73e8";
                e.currentTarget.style.backgroundColor = "#f0f7ff";
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "#ced4da";
              e.currentTarget.style.backgroundColor = "#ffffff";
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontSize: "22px" }}>🎨</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "14px", color: "#212529" }}>
                  SVG Vector Image (.svg)
                </div>
                <div style={{ fontSize: "12px", color: "#6c757d" }}>
                  Infinitely scalable, ideal for web and vector editors
                </div>
              </div>
            </div>
            <span style={{ fontSize: "16px", color: "#1a73e8" }}>↓</span>
          </button>

          {/* PNG Option */}
          <button
            onClick={handleExportPng}
            disabled={!svgContent}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 16px",
              border: "1px solid #ced4da",
              borderRadius: "8px",
              backgroundColor: "#ffffff",
              cursor: svgContent ? "pointer" : "not-allowed",
              opacity: svgContent ? 1 : 0.5,
              transition: "all 0.15s ease",
              textAlign: "left",
            }}
            onMouseEnter={(e) => {
              if (svgContent) {
                e.currentTarget.style.borderColor = "#1a73e8";
                e.currentTarget.style.backgroundColor = "#f0f7ff";
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "#ced4da";
              e.currentTarget.style.backgroundColor = "#ffffff";
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontSize: "22px" }}>🖼️</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "14px", color: "#212529" }}>
                  High-Res PNG Image (.png)
                </div>
                <div style={{ fontSize: "12px", color: "#6c757d" }}>
                  Crisp raster image for reports, documents, and slides
                </div>
              </div>
            </div>
            <span style={{ fontSize: "16px", color: "#1a73e8" }}>↓</span>
          </button>

          {/* PDF Option */}
          <button
            onClick={handleExportPdf}
            disabled={!svgContent}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "12px 16px",
              border: "1px solid #ced4da",
              borderRadius: "8px",
              backgroundColor: "#ffffff",
              cursor: svgContent ? "pointer" : "not-allowed",
              opacity: svgContent ? 1 : 0.5,
              transition: "all 0.15s ease",
              textAlign: "left",
            }}
            onMouseEnter={(e) => {
              if (svgContent) {
                e.currentTarget.style.borderColor = "#1a73e8";
                e.currentTarget.style.backgroundColor = "#f0f7ff";
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = "#ced4da";
              e.currentTarget.style.backgroundColor = "#ffffff";
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <span style={{ fontSize: "22px" }}>📄</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: "14px", color: "#212529" }}>
                  PDF Document (.pdf)
                </div>
                <div style={{ fontSize: "12px", color: "#6c757d" }}>
                  Landscape PDF formatted for printing or sharing
                </div>
              </div>
            </div>
            <span style={{ fontSize: "16px", color: "#1a73e8" }}>↓</span>
          </button>
        </div>
      </div>
    </div>
  );
}
