import {afterEach, expect, it, vi} from 'vitest';
import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {AxiosHeaders, type AxiosResponse} from 'axios';
import {api} from './api';
import GitHubUploader from './components/GitHubUploader';
import FileUploader from './components/FileUploader';
import StartButton from './components/StartButton';
import type {pyProject} from './types/types';

const project: pyProject = {projectID: 'p', projectName: 'Demo', files: []};
const imported: AxiosResponse<pyProject> = {data: project, status: 201, statusText: 'Created',
  headers: {}, config: {headers: new AxiosHeaders()}};
afterEach(() => vi.restoreAllMocks());

it('opens the GitHub dialog and posts the typed URL as JSON', async () => {
  const post = vi.spyOn(api, 'post').mockResolvedValue(imported);
  const loaded = vi.fn();
  const user = userEvent.setup();
  const {container} = render(<GitHubUploader projectName=" My project " onProjectLoaded={loaded} />);
  await user.click(screen.getByRole('button', {name: 'Import public GitHub repository'}));
  expect(container.querySelector('dialog')?.open).toBe(true);
  await user.type(screen.getByLabelText('Repository URL'), 'https://github.com/owner/repo');
  await user.click(screen.getByRole('button', {name: 'Import repository'}));
  await waitFor(() => expect(loaded).toHaveBeenCalledWith(project));
  expect(post).toHaveBeenCalledWith('/api/projects/github',
    {url: 'https://github.com/owner/repo', projectName: 'My project'}, expect.objectContaining({signal: expect.any(AbortSignal)}));
  expect(container.querySelector('dialog')?.open).toBe(false);
});

it('shows GitHub errors without replacing the current project', async () => {
  vi.spyOn(api, 'post').mockRejectedValue({isAxiosError: true,
    response: {data: {error: {message: 'No Python files were found.'}}}});
  const loaded = vi.fn();
  const user = userEvent.setup();
  const {container} = render(<GitHubUploader onProjectLoaded={loaded} />);
  await user.click(screen.getByRole('button', {name: 'Import public GitHub repository'}));
  await user.type(screen.getByLabelText('Repository URL'), 'https://github.com/owner/repo');
  await user.click(screen.getByRole('button', {name: 'Import repository'}));
  expect((await screen.findByRole('alert')).textContent).toContain('No Python files');
  expect(loaded).not.toHaveBeenCalled();
  expect(container.querySelector('dialog')?.open).toBe(true);
});

it('ignores an import response after the dialog is cancelled', async () => {
  let finish!: (result: AxiosResponse<pyProject>) => void;
  vi.spyOn(api, 'post').mockReturnValue(new Promise(resolve => {finish = resolve;}));
  const loaded = vi.fn();
  const user = userEvent.setup();
  render(<GitHubUploader onProjectLoaded={loaded} />);
  await user.click(screen.getByRole('button', {name: 'Import public GitHub repository'}));
  await user.type(screen.getByLabelText('Repository URL'), 'https://github.com/owner/repo');
  await user.click(screen.getByRole('button', {name: 'Import repository'}));
  await user.click(screen.getByRole('button', {name: 'Cancel'}));
  await act(async () => {finish(imported);});
  expect(loaded).not.toHaveBeenCalled();
});

it.each(['main.py', 'project.zip'])('sends %s to the right route with projectName', async name => {
  const post = vi.spyOn(api, 'post').mockResolvedValue(imported);
  const loaded = vi.fn();
  render(<FileUploader onProjectLoaded={loaded} projectName=" Custom " />);
  fireEvent.change(screen.getByLabelText('Python file or ZIP'), {target: {files: [new File(['content'], name)]}});
  await waitFor(() => expect(loaded).toHaveBeenCalled());
  expect(post.mock.calls[0][0]).toBe(`/api/projects/${name.endsWith('.zip') ? 'zip' : 'file'}`);
  expect((post.mock.calls[0][1] as FormData).get('projectName')).toBe('Custom');
});

it('disables the start button while generation is pending', async () => {
  const start = vi.fn();
  const user = userEvent.setup();
  const {rerender} = render(<StartButton onClick={start} />);
  await user.click(screen.getByRole('button'));
  expect(start).toHaveBeenCalledOnce();
  rerender(<StartButton onClick={start} isLoading />);
  expect((screen.getByRole('button') as HTMLButtonElement).disabled).toBe(true);
  await user.click(screen.getByRole('button'));
  expect(start).toHaveBeenCalledOnce();
});
