import {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {ReactFlow, Background, Controls, applyNodeChanges, applyEdgeChanges,
  type Node, type Edge, type OnNodesChange, type OnEdgesChange} from '@xyflow/react';
import axios from 'axios';
import '@xyflow/react/dist/style.css';
import {api, errorMessage} from '../api';
import {graphElements, graphTitle} from '../diagram';
import type {flowchartJSON, sourceFile, SourceSelection} from '../types/types';

export interface diagramManagerProperties {
  flowchart: flowchartJSON | null;
  selectedFile: sourceFile | null;
  fileViewRequest: number;
  onGraphFileSelected: (fileId: string) => void;
  onSourceSelected: (selection: SourceSelection) => void;
}

export default function DiagramManager({flowchart, selectedFile, fileViewRequest,
  onGraphFileSelected, onSourceSelected}: diagramManagerProperties) {
  const [graphId, setGraphId] = useState<string | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [error, setError] = useState<string | null>(null);
  const request = useRef<AbortController | null>(null);
  const selectedFileId = useRef(selectedFile?.fileID);
  selectedFileId.current = selectedFile?.fileID;

  useEffect(() => {
    const fileGraph = Object.values(flowchart?.graphs || {}).find(graph =>
      graph.graphType === 'file' && graph.fileId === selectedFileId.current);
    const projectGraph = Object.values(flowchart?.graphs || {}).find(graph => graph.graphType === 'project');
    setGraphId(fileGraph?.graphId || projectGraph?.graphId || null);
    setHistory([]);
  }, [flowchart, fileViewRequest]);

  const graph = graphId ? flowchart?.graphs[graphId] || null : null;
  const elements = useMemo(() => graphElements(graph), [graph]);
  useEffect(() => {
    request.current?.abort();
    setNodes(elements.nodes);
    setEdges(elements.edges);
    setError(null);
    return () => request.current?.abort();
  }, [elements]);

  const onNodesChange: OnNodesChange = useCallback(changes => setNodes(nodes => applyNodeChanges(changes, nodes)), []);
  const onEdgesChange: OnEdgesChange = useCallback(changes => setEdges(edges => applyEdgeChanges(changes, edges)), []);

  function openGraph(next: string, remember = true) {
    const target = flowchart?.graphs[next];
    if (!target) return;
    request.current?.abort();
    if (remember && graphId && next !== graphId) setHistory(history => [...history, graphId]);
    setGraphId(next);
    if (target.fileId) onGraphFileSelected(target.fileId);
  }

  function childGraph(nodeId: string): string | undefined {
    return flowchart?.graphReferences.find(reference =>
      reference.sourceGraphId === graphId && reference.sourceNodeId === nodeId)?.targetGraphId;
  }

  async function selectNode(node: Node) {
    if (!flowchart?.projectId || flowchart.revisionId === null || !graphId) return;
    const source = graph?.nodes.find(item => item.nodeId === node.id)?.sourceLocation;
    if (!source) {
      const child = childGraph(node.id);
      if (child) openGraph(child);
      return;
    }
    const controller = new AbortController();
    request.current?.abort();
    request.current = controller;
    setError(null);
    try {
      const response = await api.get<SourceSelection>(`/api/projects/${flowchart.projectId}/source-location`, {
        params: {graphId, nodeId: node.id, revisionId: flowchart.revisionId}, signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (response.data.projectId === flowchart.projectId && response.data.revisionId === flowchart.revisionId) {
        onSourceSelected(response.data);
      }
    } catch (caught) {
      if (!axios.isCancel(caught)) setError(errorMessage(caught));
    }
  }

  return <div className="diagramWorkspace">
    {flowchart && <div className="diagramToolbar">
      <button type="button" disabled={!history.length} onClick={() => {
        const previous = history[history.length - 1];
        setHistory(history => history.slice(0, -1));
        openGraph(previous, false);
      }}>Back</button>
      <label htmlFor="diagramView">View</label>
      <select id="diagramView" value={graphId || ''} onChange={event => openGraph(event.target.value)}>
        {Object.values(flowchart.graphs).map(graph =>
          <option key={graph.graphId} value={graph.graphId}>{graphTitle(flowchart, graph)}</option>)}
      </select>
    </div>}
    {error && <p role="alert">{error}</p>}
    {graph && flowchart ? <>
      <p className="diagramHint">Click a node to highlight its source. Double-click a file or function to open its view.</p>
      <div className="diagramCanvas">
        {graph.status === 'complete' ? <ReactFlow key={graph.graphId} nodes={nodes} edges={edges}
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => {void selectNode(node);}}
          onNodeDoubleClick={(_, node) => {const child = childGraph(node.id); if (child) openGraph(child);}}
          zoomOnDoubleClick={false} fitView minZoom={0.1}>
          <Background /><Controls />
        </ReactFlow> : <p className="emptyState">This view is {graph.status}. See the analysis messages below.</p>}
      </div>
      {flowchart.diagnostics.length > 0 && <details className="diagnostics">
        <summary>Analysis messages ({flowchart.diagnostics.length})</summary>
        <ul>{flowchart.diagnostics.map((diagnostic, index) => <li key={index}>{diagnostic.message}</li>)}</ul>
      </details>}
    </> : <p className="emptyState">Import a project and click Start to generate its diagrams.</p>}
  </div>;
}
