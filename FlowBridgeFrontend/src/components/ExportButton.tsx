import {useEffect, useRef, useState} from 'react';
import axios from 'axios';
import {api, apiUrl, errorMessage} from '../api';
import type {flowchartJSON, RenderResult} from '../types/types';

export default function ExportButton({flowchart}: {flowchart: flowchartJSON | null}) {
  const request = useRef<AbortController | null>(null);
  const [result, setResult] = useState<RenderResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    request.current?.abort(); setResult(null); setError(null); setLoading(false);
    return () => request.current?.abort();
  }, [flowchart?.projectId, flowchart?.revisionId]);

  async function exportDiagrams() {
    if (!flowchart?.projectId) return;
    const controller = new AbortController();
    request.current = controller;
    setLoading(true); setError(null);
    try {
      const response = await api.post<RenderResult>(`/api/projects/${flowchart.projectId}/render`, null, {
        params: {revisionId: flowchart.revisionId}, signal: controller.signal,
      });
      if (!controller.signal.aborted) setResult(response.data);
    } catch (caught) {
      if (!axios.isCancel(caught)) setError(errorMessage(caught));
    } finally {
      if (request.current === controller) setLoading(false);
    }
  }

  return <div className="exportControls">
    <button type="button" disabled={!flowchart || loading} onClick={exportDiagrams}>
      {loading ? 'Exporting…' : 'Export diagrams'}
    </button>
    {result && <a href={apiUrl(result.viewerUrl)} target="_blank" rel="noreferrer">Open SVG viewer</a>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
