import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import axios from 'axios';
import App from './App';
import ExportModal from './components/ExportModal';
import {errorMessage, REQUEST_TIMEOUT_MS} from './api';
import {filterSourceLine} from './sourceDisplay';
import WorkspaceDialog from './components/WorkspaceDialog';
import FlowchartCanvas from './components/FlowchartCanvas';

afterEach(() => {vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();});

it('keeps the selected SVG node highlighted while zooming and panning', () => {
  vi.useFakeTimers();
  const click = vi.fn();
  const {container} = render(<FlowchartCanvas svgContent='<svg><g id="statement"><rect/></g></svg>'
    highlightedNodeId="statement" onNodeClick={click} />);
  const node = () => container.querySelector('#statement')!;
  const viewport = container.querySelector('svg')!.parentElement!;
  const initialTransform = viewport.style.transform;
  act(() => {vi.advanceTimersByTime(200);});
  expect(viewport.style.transform).toBe(initialTransform);
  expect(node().classList.contains('node-highlighted')).toBe(true);
  fireEvent.click(screen.getByTitle('Zoom In'));
  expect(node().classList.contains('node-highlighted')).toBe(true);
  fireEvent.mouseDown(node(), {clientX: 100, clientY: 100});
  fireEvent.mouseUp(node());
  fireEvent.click(node());
  expect(click).toHaveBeenCalledWith('statement');
  expect(node().classList.contains('node-highlighted')).toBe(true);
});

it('filters UTF-8 comment ranges while keeping string hashes and original line numbers', () => {
  const text = 'message = "😀 # keep"  # hide';
  const startColumn = new TextEncoder().encode(text.slice(0, text.indexOf('# hide'))).length;
  const range = {fileId: 'f', startLine: 4, endLine: 4, startColumn, endColumn: new TextEncoder().encode(text).length};
  expect(filterSourceLine(text, 4, [range])).toBe('message = "😀 # keep"  ');
  expect(filterSourceLine('# whole line', 7, [{...range, startLine: 7, endLine: 7, startColumn: 0, endColumn: 12}])).toBeNull();
  expect(filterSourceLine('return 1', 9, [range])).toBe('return 1');
});

it('opens display settings and applies the comment toggle', () => {
  const change = vi.fn();
  render(<WorkspaceDialog panel="settings" project={null} hideComments={false} error={null}
    onHideComments={change} onClose={vi.fn()} />);
  fireEvent.click(screen.getByRole('checkbox', {name: 'Hide source comments'}));
  expect(change).toHaveBeenCalledWith(true);
});

it('shows workspace information without creating a sign-in flow', () => {
  render(<WorkspaceDialog panel="workspace" project={{projectID: 'p', projectName: 'Demo', files: []}}
    hideComments={false} error={null} onHideComments={vi.fn()} onClose={vi.fn()} />);
  expect(screen.getByRole('dialog', {name: 'Current workspace'})).toBeTruthy();
  expect(screen.getByText('Demo')).toBeTruthy();
  expect(screen.queryByRole('textbox')).toBeNull();
});

it('explains a timeout and keeps a finite request deadline', () => {
  expect(REQUEST_TIMEOUT_MS).toBe(90_000);
  expect(errorMessage({isAxiosError: true, code: 'ECONNABORTED'})).toContain('timed out');
  expect(errorMessage({isAxiosError: true, code: 'ERR_NETWORK'})).toContain('backend');
});

it('refuses a PNG that would exceed browser canvas limits while leaving SVG available', () => {
  const close = vi.fn();
  render(<ExportModal isOpen onClose={close} svgContent='<svg width="1200" height="30000" />' />);
  fireEvent.click(screen.getByRole('button', {name: /PNG/}));
  expect(screen.getByRole('alert').textContent).toContain('too large for PNG');
  expect((screen.getByRole('button', {name: /SVG/}) as HTMLButtonElement).disabled).toBe(false);
  expect(close).not.toHaveBeenCalled();
});

it('reports an image conversion failure instead of silently closing export', async () => {
  const revoke = vi.fn();
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = () => 'blob:test';
    static revokeObjectURL = revoke;
  });
  vi.stubGlobal('Image', class {
    onerror?: () => void;
    set src(_value: string) {queueMicrotask(() => this.onerror?.());}
  });
  const close = vi.fn();
  render(<ExportModal isOpen onClose={close} svgContent='<svg width="300" height="200" />' />);
  fireEvent.click(screen.getByRole('button', {name: /PNG/}));
  expect((await screen.findByRole('alert')).textContent).toContain('SVG version instead');
  expect(revoke).toHaveBeenCalledWith('blob:test');
  expect(close).not.toHaveBeenCalled();
});

it('handles blocked PDF popups without losing the current export', () => {
  vi.spyOn(window, 'open').mockReturnValue(null);
  const alert = vi.spyOn(window, 'alert').mockImplementation(() => {});
  const close = vi.fn();
  render(<ExportModal isOpen onClose={close} svgContent='<svg width="300" height="200" />' />);
  fireEvent.click(screen.getByRole('button', {name: /PDF/}));
  expect(alert).toHaveBeenCalledWith(expect.stringContaining('allow popups'));
  expect(close).not.toHaveBeenCalled();
});

it('selects the narrowest active source span and clears stale highlights', async () => {
  const project = {projectID: 'p', projectName: 'Highlight', files: [
    {fileID: 'f', fileName: 'main.py', filePath: 'main.py', fileContent: 'def run():\n    return 1\n\n'},
  ]};
  const span = {fileId: 'f', filePath: 'main.py', startLine: 1, endLine: 2, startColumn: 0, endColumn: 12};
  const statement = {...span, startLine: 2, startColumn: 4};
  const graphs = {
    project: {id: 'project', type: 'project', title: 'Project', svg: '<svg />', width: 300, height: 300},
    file: {id: 'file', type: 'file', title: 'main.py', width: 300, height: 300,
      svg: '<svg><g id="definition"><rect/><text>definition</text></g><g id="returned"><rect/><text>returned</text></g><g id="start"><rect/><text>Start</text></g></svg>'},
  };
  const data = {projectId: 'p', revisionId: 1, projectGraphId: 'project', graphs,
    flowchart: {files: [{fileId: 'f', fileName: 'main.py', graphId: 'file'}], functions: [], graphs: {}},
    nodeToChildGraph: {}, graphToSourceFile: {file: 'f'}, diagnostics: [], analysisFiles: [],
    sourceMapping: {files: {f: {lineToNodes: {'2': ['definition', 'returned']}}}, nodes: {
      definition: {graphId: 'file', span}, returned: {graphId: 'file', span: statement},
    }},
  };
  vi.spyOn(axios, 'post').mockResolvedValueOnce({data: project}).mockResolvedValueOnce({data});
  const {container} = render(<App />);
  fireEvent.click(screen.getByTitle(/^Upload a Python file/));
  fireEvent.change(document.getElementById('modalFileInput')!, {target: {files: [new File(['source'], 'main.py')]}});
  await waitFor(() => expect(screen.queryByRole('heading', {name: 'Import Project'})).toBeNull());
  fireEvent.click(screen.getByTitle('Generate Flowchart'));
  fireEvent.click(await screen.findByText('main.py'));
  fireEvent.click(screen.getByTitle('Line 2: Click to highlight in flowchart'));
  await waitFor(() => expect(container.querySelector('#returned')?.classList.contains('node-highlighted')).toBe(true));
  expect(container.querySelector('#definition')?.classList.contains('node-highlighted')).toBe(false);
  fireEvent.click(container.querySelector('#start')!);
  await act(async () => {});
  const line = screen.getByTitle('Line 2: Click to highlight in flowchart').parentElement!;
  expect(line.style.backgroundColor).toBe('transparent');
  fireEvent.click(screen.getByTitle('Line 3: Click to highlight in flowchart'));
  expect(container.querySelector('.node-highlighted')).toBeNull();
});
