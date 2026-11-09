import {useEffect, useRef, useState, type FormEvent} from 'react';
import axios from 'axios';
import {api, errorMessage} from '../api';
import type {pyProject} from '../types/types';

export interface linkUploaderProperties {
  onProjectLoaded: (project: pyProject) => void;
  projectName?: string;
}

// The dialog sends the same project object as file and ZIP imports.
export default function GitHubUploader({onProjectLoaded, projectName = ''}: linkUploaderProperties) {
  const dialog = useRef<HTMLDialogElement>(null);
  const request = useRef<AbortController | null>(null);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => () => request.current?.abort(), []);

  function cancel() {
    request.current?.abort();
    dialog.current?.close();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!url.trim()) return;
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    setLoading(true);
    setError(null);
    try {
      const response = await api.post<pyProject>('/api/projects/github', {
        url: url.trim(),
        ...(projectName.trim() ? {projectName: projectName.trim()} : {}),
      }, {signal: controller.signal});
      if (controller.signal.aborted) return;
      onProjectLoaded(response.data);
      setUrl('');
      dialog.current?.close();
    } catch (caught) {
      if (!axios.isCancel(caught)) setError(errorMessage(caught));
    } finally {
      if (request.current === controller) setLoading(false);
    }
  }

  return <>
    <button type="button" className="iconButton" aria-label="Import public GitHub repository"
      title="Import public GitHub repository" onClick={() => {setError(null); dialog.current?.showModal();}}>
      <img src="linkIcon.png" alt="" className="toolIcon" />
    </button>
    <dialog ref={dialog} className="importDialog" onCancel={() => request.current?.abort()}>
      <form onSubmit={submit}>
        <h2>Import a public GitHub repository</h2>
        <label htmlFor="repositoryUrl">Repository URL</label>
        <input id="repositoryUrl" type="url" placeholder="https://github.com/owner/repository"
          value={url} onChange={event => setUrl(event.target.value)} required autoFocus />
        {error && <p role="alert">{error}</p>}
        <div className="dialogActions">
          <button type="button" onClick={cancel}>Cancel</button>
          <button type="submit" disabled={loading}>{loading ? 'Importing…' : 'Import repository'}</button>
        </div>
      </form>
    </dialog>
  </>;
}
