import { useState, useCallback } from 'react';
import {ReactFlow, Background, Controls, applyNodeChanges, applyEdgeChanges, type Node, type Edge, type OnNodesChange, type OnEdgesChange} from '@xyflow/react';
import '@xyflow/react/dist/style.css'; // Required for React Flow to render properly

const nodeTypes =[
  {
    id: '3',
    type: ''
  },
];

const initialNodes= [
  { id: '1', 
    position: { x: 0, y: 0 }, 
    data: { label: 'Start' } },
  { id: '2', 
    position: { x: 0, y: 100 }, 
    data: { label: 'End' } },
];

const initialEdges= [
  { id: '1-2', source: '1', target: '2' },
];

export default function DiagramManager() {
  const [nodes, setNodes] = useState<Node[]>(initialNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);

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
      <ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} fitView>
        <Background color="black" />
        <Controls />
      </ReactFlow>
    </div>
  );
}