import React, { useState, ChangeEvent } from "react";
import axios from "axios";
import { PyProject } from "../types/flowchart";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onProjectLoaded: (project: PyProject) => void;
  apiBaseUrl?: string;
}

type TabType = "file" | "zip" | "github";

export default function UploadModal({
  isOpen,
  onClose,
  onProjectLoaded,
  apiBaseUrl = "http://localhost:8000",
}: UploadModalProps) {
  const [activeTab, setActiveTab] = useState<TabType>("file");
  const [githubUrl, setGithubUrl] = useState<string>("");
  const [githubProjectName, setGithubProjectName] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleFileUpload(e: ChangeEvent<HTMLInputElement>, isZip: boolean) {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("projectName", file.name.replace(/\.[^/.]+$/, ""));

      const endpoint = isZip
        ? `${apiBaseUrl}/api/projects/zip`
        : `${apiBaseUrl}/api/projects/file`;

      const response = await axios.post<PyProject>(endpoint, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      onProjectLoaded(response.data);
      onClose();
    } catch (err: unknown) {
      console.error("Upload failed:", err);
      const msg =
        axios.isAxiosError(err) && err.response?.data?.error?.message
          ? err.response.data.error.message
          : "Failed to upload file. Please check file format and server status.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
      e.target.value = "";
    }
  }

  async function handleGithubSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!githubUrl.trim()) {
      setErrorMessage("Please enter a valid GitHub repository URL.");
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const response = await axios.post<PyProject>(
        `${apiBaseUrl}/api/projects/github`,
        {
          url: githubUrl.trim(),
          projectName: githubProjectName.trim() || undefined,
        },
        {
          headers: { "Content-Type": "application/json" },
        }
      );

      onProjectLoaded(response.data);
      onClose();
    } catch (err: unknown) {
      console.error("GitHub import failed:", err);
      const msg =
        axios.isAxiosError(err) && err.response?.data?.error?.message
          ? err.response.data.error.message
          : "Failed to import from GitHub. Ensure the repository is public and accessible.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
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
          width: "520px",
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
            <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700 }}>Import Project</h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "12px", opacity: 0.9 }}>
              Upload a Python file, ZIP project, or enter a public GitHub repository link.
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

        {/* Tab Buttons */}
        <div
          style={{
            display: "flex",
            borderBottom: "1px solid #dee2e6",
            backgroundColor: "#f8f9fa",
          }}
        >
          <button
            onClick={() => { setActiveTab("file"); setErrorMessage(null); }}
            style={{
              flex: 1,
              padding: "12px",
              border: "none",
              background: activeTab === "file" ? "#ffffff" : "transparent",
              borderBottom: activeTab === "file" ? "3px solid #1a73e8" : "3px solid transparent",
              fontWeight: activeTab === "file" ? 700 : 500,
              color: activeTab === "file" ? "#1a73e8" : "#495057",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            📄 Python File (.py)
          </button>
          <button
            onClick={() => { setActiveTab("zip"); setErrorMessage(null); }}
            style={{
              flex: 1,
              padding: "12px",
              border: "none",
              background: activeTab === "zip" ? "#ffffff" : "transparent",
              borderBottom: activeTab === "zip" ? "3px solid #1a73e8" : "3px solid transparent",
              fontWeight: activeTab === "zip" ? 700 : 500,
              color: activeTab === "zip" ? "#1a73e8" : "#495057",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            📦 ZIP Project (.zip)
          </button>
          <button
            onClick={() => { setActiveTab("github"); setErrorMessage(null); }}
            style={{
              flex: 1,
              padding: "12px",
              border: "none",
              background: activeTab === "github" ? "#ffffff" : "transparent",
              borderBottom: activeTab === "github" ? "3px solid #1a73e8" : "3px solid transparent",
              fontWeight: activeTab === "github" ? 700 : 500,
              color: activeTab === "github" ? "#1a73e8" : "#495057",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            🐙 GitHub Repo
          </button>
        </div>

        {/* Tab Body */}
        <div style={{ padding: "24px" }}>
          {errorMessage && (
            <div
              style={{
                backgroundColor: "#ffebee",
                color: "#c62828",
                padding: "10px 14px",
                borderRadius: "8px",
                fontSize: "13px",
                marginBottom: "16px",
                border: "1px solid #ffcdd2",
              }}
            >
              {errorMessage}
            </div>
          )}

          {isLoading ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "30px 0",
                gap: "12px",
              }}
            >
              <div
                style={{
                  width: "40px",
                  height: "40px",
                  border: "4px solid #e3f2fd",
                  borderTop: "4px solid #1a73e8",
                  borderRadius: "50%",
                  animation: "spin 1s linear infinite",
                }}
              />
              <span style={{ fontSize: "14px", fontWeight: 600, color: "#1a73e8" }}>
                Importing and loading project...
              </span>
            </div>
          ) : (
            <>
              {activeTab === "file" && (
                <div style={{ textAlign: "center" }}>
                  <label
                    htmlFor="modalFileInput"
                    style={{
                      display: "block",
                      border: "2px dashed #b0bec5",
                      borderRadius: "10px",
                      padding: "36px 20px",
                      cursor: "pointer",
                      backgroundColor: "#fafafa",
                      transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = "#1a73e8";
                      e.currentTarget.style.backgroundColor = "#f0f7ff";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = "#b0bec5";
                      e.currentTarget.style.backgroundColor = "#fafafa";
                    }}
                  >
                    <div style={{ fontSize: "36px", marginBottom: "8px" }}>📄</div>
                    <div style={{ fontWeight: 600, fontSize: "15px", color: "#212529" }}>
                      Click to choose a Python file
                    </div>
                    <div style={{ fontSize: "12px", color: "#6c757d", marginTop: "4px" }}>
                      Supports single .py scripts
                    </div>
                  </label>
                  <input
                    id="modalFileInput"
                    type="file"
                    accept=".py"
                    style={{ display: "none" }}
                    onChange={(e) => handleFileUpload(e, false)}
                  />
                </div>
              )}

              {activeTab === "zip" && (
                <div style={{ textAlign: "center" }}>
                  <label
                    htmlFor="modalZipInput"
                    style={{
                      display: "block",
                      border: "2px dashed #b0bec5",
                      borderRadius: "10px",
                      padding: "36px 20px",
                      cursor: "pointer",
                      backgroundColor: "#fafafa",
                      transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = "#1a73e8";
                      e.currentTarget.style.backgroundColor = "#f0f7ff";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = "#b0bec5";
                      e.currentTarget.style.backgroundColor = "#fafafa";
                    }}
                  >
                    <div style={{ fontSize: "36px", marginBottom: "8px" }}>📦</div>
                    <div style={{ fontWeight: 600, fontSize: "15px", color: "#212529" }}>
                      Click to choose a ZIP project archive
                    </div>
                    <div style={{ fontSize: "12px", color: "#6c757d", marginTop: "4px" }}>
                      Supports multi-file projects with directories (e.g. example_project.zip)
                    </div>
                  </label>
                  <input
                    id="modalZipInput"
                    type="file"
                    accept=".zip"
                    style={{ display: "none" }}
                    onChange={(e) => handleFileUpload(e, true)}
                  />
                </div>
              )}

              {activeTab === "github" && (
                <form onSubmit={handleGithubSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "13px", fontWeight: 600, marginBottom: "6px" }}>
                      GitHub Repository URL *
                    </label>
                    <input
                      type="url"
                      placeholder="https://github.com/username/repository"
                      value={githubUrl}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      required
                      style={{
                        width: "100%",
                        padding: "10px 12px",
                        borderRadius: "6px",
                        border: "1px solid #ced4da",
                        fontSize: "14px",
                        outline: "none",
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "13px", fontWeight: 600, marginBottom: "6px" }}>
                      Project Name (optional)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. MyProject"
                      value={githubProjectName}
                      onChange={(e) => setGithubProjectName(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "10px 12px",
                        borderRadius: "6px",
                        border: "1px solid #ced4da",
                        fontSize: "14px",
                        outline: "none",
                      }}
                    />
                  </div>

                  <button
                    type="submit"
                    style={{
                      marginTop: "6px",
                      backgroundColor: "#1a73e8",
                      color: "#ffffff",
                      border: "none",
                      borderRadius: "6px",
                      padding: "12px",
                      fontSize: "14px",
                      fontWeight: 600,
                      cursor: "pointer",
                      transition: "background-color 0.15s",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#1557b0")}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "#1a73e8")}
                  >
                    Import from GitHub
                  </button>
                </form>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
