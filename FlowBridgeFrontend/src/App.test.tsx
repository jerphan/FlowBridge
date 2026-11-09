import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import axios from 'axios';
import App from './App';
import UploadModal from './components/UploadModal';
import type {PyProject} from './types/flowchart';

const project: PyProject = {projectID: 'p1', projectName: 'Nested', files: [
  {fileID: 'a', fileName: 'main.py', filePath: 'app/main.py', fileContent: 'one = 1\r\n'},
  {fileID: 'b', fileName: 'main.py', filePath: 'tools/main.py', fileContent: 'two = 2\r\n'},
]};

function diagrams(input = project) {
  return {
    projectId: input.projectID, revisionId: 1, projectName: input.projectName,
    projectGraphId: 'project-graph', status: 'success', analysisStatus: 'success',
    graphs: {
      'project-graph': {id: 'project-graph', type: 'project', title: 'Old project diagram',
        svg: '<svg><g id="a-card" data-node-id="a-card"><text>old diagram</text></g></svg>', width: 400, height: 300},
      'a-graph': {id: 'a-graph', type: 'file', title: 'app/main.py', svg: '<svg><text>one flow</text></svg>', width: 400, height: 300},
      'b-graph': {id: 'b-graph', type: 'file', title: 'tools/main.py', svg: '<svg><text>two flow</text></svg>', width: 400, height: 300},
    },
    flowchart: {files: input.files.map((file, i) => ({fileId: file.fileID, fileName: file.fileName,
      filePath: file.filePath, graphId: i ? 'b-graph' : 'a-graph'})), functions: [], graphs: {}},
    nodeToChildGraph: {'a-card': 'a-graph'}, graphToSourceFile: {'a-graph': 'a', 'b-graph': 'b'},
    sourceMapping: {files: {}, nodes: {}}, diagnostics: [], analysisFiles: [],
  };
}

async function upload(name = 'project.py') {
  fireEvent.click(screen.getByTitle(/^Upload a Python file/));
  fireEvent.click(screen.getByRole('button', {name: /Python File/}));
  fireEvent.change(document.getElementById('modalFileInput')!, {
    target: {files: [new File(['value = 1'], name, {type: 'text/x-python'})]},
  });
  await waitFor(() => expect(screen.queryByRole('heading', {name: 'Import Project'})).toBeNull());
}

afterEach(() => vi.restoreAllMocks());

it('starts a new project with an empty workspace and opens import', async () => {
  vi.spyOn(axios, 'post').mockResolvedValueOnce({data: project}).mockResolvedValueOnce({data: diagrams()});
  render(<App />);
  await upload();
  fireEvent.click(screen.getByTitle('Generate Flowchart'));
  await screen.findByText('old diagram');
  fireEvent.click(screen.getByText('tools/main.py'));
  expect(await screen.findByText('two = 2')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Start New Project'}));
  expect(screen.getByRole('heading', {name: 'Import Project'})).toBeTruthy();
  expect(screen.queryByText('two = 2')).toBeNull();
  expect(screen.queryByText('two flow')).toBeNull();
  expect((screen.getByTitle('Upload a file or zip first') as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByTitle('Generate a diagram to export') as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', {name: '✕'}));
  expect(screen.queryByRole('heading', {name: 'Import Project'})).toBeNull();
  expect(screen.getByText('No Flowchart Generated Yet')).toBeTruthy();
});

it('cancels a pending diagram when starting over and ignores its late response', async () => {
  let complete!: (value: unknown) => void;
  const post = vi.spyOn(axios, 'post').mockResolvedValueOnce({data: project})
    .mockImplementationOnce(() => new Promise(resolve => {complete = resolve;}));
  render(<App />);
  await upload();
  fireEvent.click(screen.getByTitle('Generate Flowchart'));
  const pending = post.mock.calls[1][2]?.signal as AbortSignal;
  fireEvent.click(screen.getByRole('button', {name: 'Start New Project'}));
  expect(pending.aborted).toBe(true);
  await act(async () => {complete({data: diagrams()});});
  expect(screen.queryByText('old diagram')).toBeNull();
  expect((screen.getByTitle('Upload a file or zip first') as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('heading', {name: 'Import Project'})).toBeTruthy();
});

it('uses file identity for duplicate basenames and displays their paths', async () => {
  vi.spyOn(axios, 'post').mockResolvedValueOnce({data: project}).mockResolvedValueOnce({data: diagrams()});
  render(<App />);
  await upload();
  fireEvent.click(screen.getByTitle('Generate Flowchart'));
  fireEvent.click(await screen.findByText('tools/main.py'));
  expect(await screen.findByText('two = 2')).toBeTruthy();
  expect(screen.queryByText('one = 1')).toBeNull();
  expect(screen.getByText('two flow')).toBeTruthy();
});

it('ignores an old render even when the transport completes after cancellation', async () => {
  let complete!: (value: unknown) => void;
  const next: PyProject = {projectID: 'p2', projectName: 'New', files: [
    {fileID: 'c', fileName: 'new.py', filePath: 'new.py', fileContent: 'new_value = 2\n'},
  ]};
  const post = vi.spyOn(axios, 'post')
    .mockResolvedValueOnce({data: project})
    .mockImplementationOnce(() => new Promise(resolve => {complete = resolve;}))
    .mockResolvedValueOnce({data: next});
  render(<App />);
  await upload();
  fireEvent.click(screen.getByTitle('Generate Flowchart'));
  await upload('new.py');
  await act(async () => {complete({data: diagrams()});});
  expect((post.mock.calls[1][2]?.signal as AbortSignal).aborted).toBe(true);
  fireEvent.click(screen.getByText('new.py'));
  expect(screen.getByText('new_value = 2')).toBeTruthy();
  expect(screen.queryByText('old diagram')).toBeNull();
  expect((screen.getByTitle('Generate Flowchart') as HTMLButtonElement).disabled).toBe(false);
});

it('rejects a render response for another project', async () => {
  vi.spyOn(axios, 'post').mockResolvedValueOnce({data: project})
    .mockResolvedValueOnce({data: {...diagrams(), projectId: 'other'}});
  vi.spyOn(console, 'error').mockImplementation(() => {});
  render(<App />);
  await upload();
  fireEvent.click(screen.getByTitle('Generate Flowchart'));
  expect(await screen.findByText('The request could not be completed. Please try again.')).toBeTruthy();
  expect(screen.queryByText('old diagram')).toBeNull();
});

it('shows a backend generation error while retaining the uploaded source', async () => {
  vi.spyOn(axios, 'post').mockResolvedValueOnce({data: project})
    .mockRejectedValueOnce({isAxiosError: true, response: {data: {error: {message: 'Could not export diagrams.'}}}});
  vi.spyOn(console, 'error').mockImplementation(() => {});
  render(<App />);
  await upload();
  fireEvent.click(screen.getByTitle('Generate Flowchart'));
  expect(await screen.findByText('Could not export diagrams.')).toBeTruthy();
  fireEvent.click(screen.getByText('app/main.py'));
  expect(screen.getByText('one = 1')).toBeTruthy();
});

it('imports GitHub using the URL JSON contract', async () => {
  const post = vi.spyOn(axios, 'post').mockResolvedValue({data: project});
  const loaded = vi.fn();
  render(<UploadModal isOpen onClose={vi.fn()} onProjectLoaded={loaded} />);
  fireEvent.click(screen.getByRole('button', {name: /GitHub Repo/}));
  fireEvent.change(screen.getByPlaceholderText('https://github.com/username/repository'), {
    target: {value: 'https://github.com/demo/repo'},
  });
  fireEvent.change(screen.getByPlaceholderText('e.g. MyProject'), {target: {value: ' Demo '}});
  fireEvent.submit(screen.getByRole('button', {name: 'Import from GitHub'}).closest('form')!);
  await waitFor(() => expect(loaded).toHaveBeenCalledWith(project));
  expect(post).toHaveBeenCalledWith('http://localhost:8000/api/projects/github',
    {url: 'https://github.com/demo/repo', projectName: 'Demo'}, expect.objectContaining({signal: expect.any(AbortSignal)}));
});

it('does not replace the project when a dismissed import eventually finishes', async () => {
  let complete!: (value: unknown) => void;
  vi.spyOn(axios, 'post').mockImplementationOnce(() => new Promise(resolve => {complete = resolve;}));
  const loaded = vi.fn();
  render(<UploadModal isOpen onClose={vi.fn()} onProjectLoaded={loaded} />);
  fireEvent.click(screen.getByRole('button', {name: /GitHub Repo/}));
  fireEvent.change(screen.getByPlaceholderText('https://github.com/username/repository'), {
    target: {value: 'https://github.com/demo/repo'},
  });
  fireEvent.submit(screen.getByRole('button', {name: 'Import from GitHub'}).closest('form')!);
  fireEvent.click(screen.getByRole('button', {name: '✕'}));
  await act(async () => {complete({data: project});});
  expect(loaded).not.toHaveBeenCalled();
});
