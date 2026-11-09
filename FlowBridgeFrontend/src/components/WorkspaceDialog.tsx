import {useEffect, useRef} from 'react';
import type {PyProject} from '../types/flowchart';

interface Props {
  panel: 'settings' | 'workspace' | null;
  project: PyProject | null;
  hideComments: boolean;
  error: string | null;
  onHideComments: (value: boolean) => void;
  onClose: () => void;
}

export default function WorkspaceDialog({panel, project, hideComments, error, onHideComments, onClose}: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (panel && !dialog.current?.open) dialog.current?.showModal();
    if (!panel && dialog.current?.open) dialog.current.close();
  }, [panel]);
  return <dialog ref={dialog} className="workspaceDialog" aria-label={panel === 'settings' ? 'Display settings' : 'Current workspace'}
    onCancel={onClose} onClick={event => {if (event.target === event.currentTarget) onClose();}}>
    <section>
      <header><h2>{panel === 'settings' ? 'Display settings' : 'Current workspace'}</h2>
        <button type="button" onClick={onClose} aria-label="Close panel">×</button></header>
      <div className="workspaceDialogBody">
        {panel === 'settings' ? <>
          <label className="displayOption"><input type="checkbox" checked={hideComments}
            onChange={event => onHideComments(event.target.checked)} /> Hide source comments</label>
          <p>Hide comments and docstrings in the source pane. Original files and line numbers stay unchanged.</p>
          {error && <p role="alert" className="panelError">{error}</p>}
        </> : <>
          <dl><dt>Project</dt><dd>{project?.projectName || 'No project loaded'}</dd>
            <dt>Python files</dt><dd>{project?.files.length || 0}</dd>
            <dt>Storage</dt><dd>Temporary local session</dd></dl>
          <p>No sign-in or database is needed. Inactive projects expire when memory is needed for new imports. Restarting the server clears the session.</p>
        </>}
      </div>
    </section>
  </dialog>;
}
