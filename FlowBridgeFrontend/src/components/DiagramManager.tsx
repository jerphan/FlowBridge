import { useState, useCallback, useEffect, useMemo } from 'react';
import { ReactFlow, Background, Controls, applyNodeChanges, applyEdgeChanges, type Node, type Edge, type OnNodesChange, type OnEdgesChange} from '@xyflow/react';
import '@xyflow/react/dist/style.css'; // Required for React Flow to render properly
import { flowchartJSON, flowGraph, sourceFile } from '../types/types';

export interface diagramManagerProperties {
  //The flowchartJSON JSON structure returned when StartButton is clicked
  flowchart?: flowchartJSON | null;
  //The currently selected file shown in ProjectViewer component
  selectedFile?: sourceFile | null;
}

//Function to grab the file graph for the currently selected file
export function getFileGraphForSelectedFile(
  flowchart: flowchartJSON | null | undefined,
  selectedFile: sourceFile | null | undefined
): flowGraph | null {
  if (!flowchart || !flowchart.graphs) {
    return null;
  }

  //Only parse graphs whose graphType is "file"
  const fileGraphs = Object.values(flowchart.graphs).filter(
    (graph) => graph.graphType === 'file'
  );

  if (fileGraphs.length === 0) {
    return null;
  }

  if (!selectedFile) {
    return fileGraphs[0];
  }

  //Direct match by fileId === selectedFile.fileID
  const directMatch = fileGraphs.find(
    (graph) => graph.fileId === selectedFile.fileID
  );
  if (directMatch) {
    return directMatch;
  }

  //Match via flowchartJSON.files metadata (by fileId, filePath, or fileName)
  const matchedFileMetadata = flowchart.files?.find(
    (file) =>
      file.fileId === selectedFile.fileID ||
      file.filePath === selectedFile.filePath ||
      file.fileName === selectedFile.fileName
  );

  if (matchedFileMetadata) {
    const graphById = flowchart.graphs[matchedFileMetadata.graphId];
    if (graphById && graphById.graphType === 'file') {
      return graphById;
    }

    const graphByFileId = fileGraphs.find(
      (graph) => graph.fileId === matchedFileMetadata.fileId
    );
    if (graphByFileId) {
      return graphByFileId;
    }
  }

  return null;
}

//Converting the file graph nodes to nodes that will be able to be displayed by the ReactFlow element
export function parseFileGraphNodes(fileGraph: flowGraph | null): Node[] {
  if (!fileGraph || fileGraph.graphType !== 'file') {
    return [];
  }

  return fileGraph.nodes.map((node, index) => ({
    id: node.nodeId,
    position: { x: 0, y: index * 100 },
    data: {
      label: node.label,
      nodeType: node.nodeType,
      sourceLocation: node.sourceLocation,
      graphId: fileGraph.graphId,
    },
  }));
}

//Converting the edges stored in the JSON object to ones that will be understood by ReactFlow
export function parseFileGraphEdges(fileGraph: flowGraph | null): Edge[] {
  if (!fileGraph || fileGraph.graphType !== 'file') {
    return [];
  }

  return fileGraph.edges.map((edge) => ({
    id: edge.edgeId,
    source: edge.sourceId,
    target: edge.targetId,
    edgeType: edge.edgeType ?? undefined,
  }));
}

export default function DiagramManager({
  flowchart = null,
  selectedFile = null,
}: diagramManagerProperties) {
  const activeFileGraph = useMemo(
    () => getFileGraphForSelectedFile(flowchart, selectedFile),
    [flowchart, selectedFile]
  );

  const [nodes, setNodes] = useState<Node[]>(() =>
    parseFileGraphNodes(activeFileGraph)
  );
  const [edges, setEdges] = useState<Edge[]>(() =>
    parseFileGraphEdges(activeFileGraph)
  );

  useEffect(() => {
    setNodes(parseFileGraphNodes(activeFileGraph));
    setEdges(parseFileGraphEdges(activeFileGraph));
  }, [activeFileGraph]);

  const onNodesChange: OnNodesChange = useCallback(
    (changes) => setNodes((nds) => applyNodeChanges(changes, nds)),
    []
  );
  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    []
  );

  return (
    <div style={{ width: '100%', height: '100%' }}>
      {activeFileGraph ? (
        <ReactFlow key={activeFileGraph.graphId} nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} fitView>
          <Background/>
          <Controls />
        </ReactFlow>
      ) : (
        <div>Click Start to load the flowchart.</div>
      )}
    </div>
  );
}