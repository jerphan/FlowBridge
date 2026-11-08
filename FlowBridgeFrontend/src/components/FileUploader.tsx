import { ChangeEvent, useState } from "react";
import axios from "axios";
import "../App.css";
import { PyProject } from "../types/flowchart";

type UploadStatus = "idle" | "uploading" | "success" | "error";

interface FileUploaderProps {
  onProjectLoaded: (project: PyProject) => void;
  onError?: (errorMessage: string) => void;
  apiBaseUrl?: string;
}

export default function FileUploader({
  onProjectLoaded,
  onError,
  apiBaseUrl = "http://localhost:8000",
}: FileUploaderProps) {
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [fileName, setFileName] = useState<string>("");

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setFileName(selectedFile.name);
    setStatus("uploading");

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("projectName", selectedFile.name.replace(/\.[^/.]+$/, ""));

      const isZip = selectedFile.name.toLowerCase().endsWith(".zip");
      const endpoint = isZip ? `${apiBaseUrl}/api/projects/zip` : `${apiBaseUrl}/api/projects/file`;

      const response = await axios.post<PyProject>(endpoint, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setStatus("success");
      onProjectLoaded(response.data);
    } catch (err: unknown) {
      console.error("Upload failed:", err);
      setStatus("error");
      const message = axios.isAxiosError(err) && err.response?.data?.error?.message
        ? err.response.data.error.message
        : "Failed to upload project. Ensure backend is running.";
      if (onError) onError(message);
    } finally {
      // Reset input value so re-selecting the same file triggers onChange
      e.target.value = "";
    }
  }

  return (
    <>
      <label
        htmlFor="fileUpload"
        title={
          status === "uploading"
            ? "Uploading..."
            : fileName
            ? `Uploaded: ${fileName} (Click to upload another)`
            : "Upload Python File (.py) or Project (.zip)"
        }
        style={{ cursor: "pointer", display: "inline-block" }}
      >
        <img
          src="UploadFileButton.png"
          alt="Upload Icon"
          className="toolIcon"
          style={{
            opacity: status === "uploading" ? 0.5 : 0.85,
            filter: status === "success" ? "drop-shadow(0 0 4px #2e7d32)" : undefined,
          }}
        />
      </label>
      <input
        type="file"
        id="fileUpload"
        className="toolButton"
        accept=".py,.zip"
        onChange={handleFileChange}
      />
    </>
  );
}
