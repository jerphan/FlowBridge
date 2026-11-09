import {useEffect, useRef} from 'react';
import {lineRange} from '../sourceRange';
import type {pyProject, sourceFile, sourceLocation} from '../types/types';

export interface projectViewerProperties {
  project: pyProject | null;
  selectedFileId: string | null;
  highlight: sourceLocation | null;
  onSelectFile: (file: sourceFile) => void;
}

export default function ProjectViewer({project, selectedFileId, highlight, onSelectFile}: projectViewerProperties) {
  const code = useRef<HTMLDivElement>(null);
  const file = project?.files.find(file => file.fileID === selectedFileId);
  const location = highlight?.fileId === file?.fileID ? highlight : null;
  useEffect(() => {
    code.current?.querySelector('mark')?.scrollIntoView?.({block: 'nearest'});
  }, [location]);

  return <div className="projectFileExplorer">
    <ul className="projectFileList" aria-label="Project source files">
      {project?.files.map(file => <li key={file.fileID}>
        <button type="button" className="fileListCard" aria-pressed={file.fileID === selectedFileId}
          onClick={() => onSelectFile(file)}>{file.filePath}</button>
      </li>)}
    </ul>
    <div ref={code} className="projectFileDetail">
      {file ? <>
        <p className="sourceCaption" role="status">{file.filePath}
          {location && ` • lines ${location.startLine}–${location.endLine}`}</p>
        <pre className="filePreview"><code>
          {file.fileContent.split(/\r\n|\n|\r/).map((text, index) => {
            const range = location ? lineRange(text, index + 1, location) : null;
            return <div key={index} className={`fileCodeLine${range ? ' selectedSourceLine' : ''}`}>
              <span className="fileLineNumber">{index + 1}</span>
              <span className="fileLineText">{range ? <>
                {text.slice(0, range[0])}<mark>{text.slice(range[0], range[1])}</mark>{text.slice(range[1])}
              </> : text || ' '}</span>
            </div>;
          })}
        </code></pre>
      </> : <p className="emptyState">Import a project to view its source.</p>}
    </div>
  </div>;
}
