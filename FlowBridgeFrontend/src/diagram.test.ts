import {describe, expect, it} from 'vitest';
import {graphElements, graphTitle} from './diagram';
import type {flowGraph, flowchartJSON, graphType} from './types/types';

const graph: flowGraph = {graphId: 'g', graphType: 'file', status: 'complete', fileId: 'f', functionId: null,
  nodes: [
    {nodeId: 'condition', nodeType: 'condition', label: 'x > 0', sourceLocation: null},
    {nodeId: 'left', nodeType: 'return', label: 'return 1', sourceLocation: null},
    {nodeId: 'right', nodeType: 'return', label: 'return 0', sourceLocation: null},
  ], edges: [
    {edgeId: 'true-edge', sourceId: 'condition', targetId: 'left', edgeType: 'true', label: null},
    {edgeId: 'false-edge', sourceId: 'condition', targetId: 'right', edgeType: 'false', label: null},
  ]};

describe('diagram adapter', () => {
  it.each<graphType>(['project', 'file', 'module', 'function'])('renders %s graphs with their original IDs and edges', graphType => {
    const elements = graphElements({...graph, graphType});
    expect(elements.nodes.map(node => node.id)).toEqual(['condition', 'left', 'right']);
    expect(elements.edges.map(edge => [edge.id, edge.source, edge.target, edge.label])).toEqual([
      ['true-edge', 'condition', 'left', 'true'], ['false-edge', 'condition', 'right', 'false'],
    ]);
    expect(new Set(elements.nodes.map(node => `${node.position.x},${node.position.y}`)).size).toBe(3);
  });

  it('preserves dependency labels and handles cycles', () => {
    const elements = graphElements({...graph, edges: [
      {edgeId: 'a', sourceId: 'condition', targetId: 'left', edgeType: 'next', label: 'imports'},
      {edgeId: 'b', sourceId: 'left', targetId: 'condition', edgeType: 'back', label: null},
    ]});
    expect(elements.edges[0].label).toBe('imports');
    expect(elements.nodes.every(node => Number.isFinite(node.position.x) && Number.isFinite(node.position.y))).toBe(true);
  });

  it('uses full paths to distinguish duplicate basenames', () => {
    const flowchart = {files: [{fileId: 'f', filePath: 'tests/main.py'}], functions: []} as unknown as flowchartJSON;
    expect(graphTitle(flowchart, graph)).toBe('tests/main.py • File flow');
  });
});
