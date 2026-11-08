import {useRef, useState} from 'react';
import FileUploader from './components/FileUploader';
import GitHubUploader from './components/GitHubUploader';
import StartButton from './components/StartButton';
import ProjectViewer from './components/ProjectViewer';
import DiagramManager from './components/DiagramManager';
import ExportButton from './components/ExportButton';
import type {flowchartJSON, pyProject, sourceFile, sourceLocation, SourceSelection} from './types/types';

export default function App() {
  const [project, setProject] = useState<pyProject | null>(null);
  const [selectedFile, setSelectedFile] = useState<sourceFile | null>(null);
  const [flowchart, setFlowchart] = useState<flowchartJSON | null>(null);
  const [highlight, setHighlight] = useState<sourceLocation | null>(null);
  const [fileViewRequest, setFileViewRequest] = useState(0);
  const currentProject = useRef<string | null>(null);
  const currentFlowchart = useRef<flowchartJSON | null>(null);

  function loadedProject(project: pyProject) {
    currentProject.current = project.projectID;
    currentFlowchart.current = null;
    setProject(project); setSelectedFile(project.files[0] || null);
    setFlowchart(null); setHighlight(null);
    setFileViewRequest(count => count + 1);
  }

  function selectFile(file: sourceFile) {
    setSelectedFile(file); setHighlight(null);
    setFileViewRequest(count => count + 1);
  }

  function selectSource(selection: SourceSelection) {
    if (selection.projectId !== currentProject.current ||
        selection.revisionId !== currentFlowchart.current?.revisionId) return;
    setSelectedFile(selection.file); setHighlight(selection.location);
  }

  function loadedFlowchart(flowchart: flowchartJSON) {
    if (flowchart.projectId !== currentProject.current) return;
    currentFlowchart.current = flowchart;
    setFlowchart(flowchart);
  }

  return <>
    <header className="heading">
      <div className="headingLeft"><img src="FlowBridgeIcon.png" alt="" className="logoIcon" />
        <h1 className="brandName">FlowBridge</h1></div>
      <StartButton project={project} onFlowChartLoaded={loadedFlowchart} />
      <ExportButton flowchart={flowchart} />
    </header>
    <div className="workspace">
      <aside className="sidebarLeft" aria-label="Project imports">
        <div className="toolbarTop">
          <FileUploader onProjectLoaded={loadedProject} />
          <GitHubUploader onProjectLoaded={loadedProject} />
        </div>
      </aside>
      <main className="contentGrid">
        <section className="card" aria-label="Source code">
          <h2 className="cardHeader">{project?.projectName || 'Source code'}</h2>
          <ProjectViewer project={project} selectedFileId={selectedFile?.fileID || null}
            highlight={highlight} onSelectFile={selectFile} />
        </section>
        <section className="card" aria-label="Flowchart">
          <h2 className="cardHeader">Flowchart</h2>
          <div className="cardBody"><DiagramManager flowchart={flowchart} selectedFile={selectedFile}
            fileViewRequest={fileViewRequest} onSourceSelected={selectSource}
            onGraphFileSelected={fileId => {
              const file = project?.files.find(file => file.fileID === fileId);
              if (file) {setSelectedFile(file); setHighlight(null);}
            }} /></div>
        </section>
      </main>
    </div>
  </>;
}
