import {useEffect, useRef, useState, type ChangeEvent} from 'react';
import axios from 'axios';
import {api, errorMessage} from '../api';
import type {pyProject} from '../types/types';

export interface fileUploaderProperties {
  onProjectLoaded: (project: pyProject) => void;
  projectName?: string;
}

export default function FileUploader({onProjectLoaded, projectName = ''}: fileUploaderProperties) {
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => () => request.current?.abort(), []);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    const name = file.name.toLowerCase();
    if (!name.endsWith('.py') && !name.endsWith('.zip')) {
      setError('Choose a Python file or ZIP archive.');
      return;
    }
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    setLoading(true);
    setError(null);
    const body = new FormData();
    body.append('file', file);
    if (projectName.trim()) body.append('projectName', projectName.trim());
    try {
      const route = name.endsWith('.zip') ? 'zip' : 'file';
      const response = await api.post<pyProject>(`/api/projects/${route}`, body, {signal: controller.signal});
      if (!controller.signal.aborted) onProjectLoaded(response.data);
    } catch (caught) {
      if (!axios.isCancel(caught)) setError(errorMessage(caught));
    } finally {
      if (request.current === controller) setLoading(false);
    }
  }

  return <>
    <button type="button" className="iconButton" aria-label="Upload Python file or ZIP" disabled={loading}
      title={loading ? 'Importing…' : 'Upload Python file or ZIP'} onClick={() => input.current?.click()}>
      <img src="UploadFileButton.png" alt="" className="toolIcon" />
    </button>
    <input ref={input} type="file" id="fileUpload" aria-label="Python file or ZIP"
      accept=".py,.zip" hidden onChange={upload} />
    {error && <p role="alert" className="toolbarError">{error}</p>}
  </>;
}
