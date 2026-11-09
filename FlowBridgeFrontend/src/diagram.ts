import {graphlib, layout} from '@dagrejs/dagre';
import {MarkerType, Position, type Edge, type Node} from '@xyflow/react';
import type {flowchartJSON, flowGraph} from './types/types';

export function graphTitle(flowchart: flowchartJSON, graph: flowGraph): string {
  if (graph.graphType === 'project') return 'Project overview';
  const file = flowchart.files.find(file => file.fileId === graph.fileId);
  const name = file?.filePath || 'File';
  if (graph.graphType === 'function') {
    const fn = flowchart.functions.find(fn => fn.functionId === graph.functionId);
    return `${name} • ${fn?.functionName || 'Function'}()${fn ? ` • line ${fn.startLine}` : ''}`;
  }
  return `${name} • ${graph.graphType === 'module' ? 'Module flow' : 'File flow'}`;
}

// Layout stays in Diagram Manager; the parser's graph and source IDs are preserved.
export function graphElements(graph: flowGraph | null): {nodes: Node[]; edges: Edge[]} {
  if (!graph) return {nodes: [], edges: []};
  const positions = new graphlib.Graph({multigraph: true});
  positions.setGraph({rankdir: 'TB', nodesep: 70, ranksep: 75});
  positions.setDefaultEdgeLabel(() => ({}));
  for (const node of graph.nodes) positions.setNode(node.nodeId, {width: 240, height: 76});
  for (const edge of graph.edges) positions.setEdge(edge.sourceId, edge.targetId, {}, edge.edgeId);
  layout(positions);
  const nodes: Node[] = graph.nodes.map(node => {
    const position = positions.node(node.nodeId);
    return {
      id: node.nodeId,
      position: {x: position.x - 120, y: position.y - 38},
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      style: {width: 240, minHeight: 76},
      data: {label: node.label, graphId: graph.graphId, sourceLocation: node.sourceLocation},
    };
  });
  const edges: Edge[] = graph.edges.map(edge => ({
    id: edge.edgeId, source: edge.sourceId, target: edge.targetId,
    label: edge.label || (edge.edgeType === 'next' ? undefined : edge.edgeType),
    markerEnd: {type: MarkerType.ArrowClosed},
    style: {stroke: edge.edgeType === 'false' ? '#b91c1c' : '#2563eb', strokeWidth: 2},
    data: {edgeType: edge.edgeType},
  }));
  return {nodes, edges};
}
