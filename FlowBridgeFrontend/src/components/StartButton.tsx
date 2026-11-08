import {useEffect, useRef, useState} from 'react';
import axios from 'axios';
import {api, errorMessage} from '../api';
import type {flowchartJSON, pyProject} from '../types/types';

export interface startButtonProperties {
  project: pyProject | null;
  onFlowChartLoaded: (flowchart: flowchartJSON) => void;
  revisionId?: number;
}

export default function StartButton({project, onFlowChartLoaded, revisionId = 1}: startButtonProperties) {
  const request = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    request.current?.abort();
    setLoading(false);
    setError(null);
    return () => request.current?.abort();
  }, [project?.projectID, revisionId]);

  async function analyze() {
    if (!project) return;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    setLoading(true);
    setError(null);
    try {
      const response = await api.get<flowchartJSON>(`/api/projects/${project.projectID}/flowchart`, {
        params: {revisionId}, signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (response.data.projectId !== project.projectID || response.data.revisionId !== revisionId) {
        setError('The analysis does not match the current project. Click Start again.');
        return;
      }
      onFlowChartLoaded(response.data);
    } catch (caught) {
      if (!axios.isCancel(caught)) setError(errorMessage(caught));
    } finally {
      if (request.current === controller) setLoading(false);
    }
  }

  return <div className="headingCenter">
    <button type="button" className="startButton" aria-label="Analyze project" onClick={analyze}
      disabled={!project || loading}>
      <img src="StartButton.png" alt="Start" />
    </button>
    {loading && <span role="status">Analyzing…</span>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
