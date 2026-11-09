import {expect, it, vi} from 'vitest';
import {render, screen, fireEvent} from '@testing-library/react';
import {lineRange, utf8ColumnIndex} from './sourceRange';
import ProjectViewer from './components/ProjectViewer';
import type {pyProject, sourceLocation} from './types/types';

it('converts UTF-8 columns including emoji to string indexes', () => {
  const prefix = '\t😀 café';
  expect(utf8ColumnIndex(prefix + ' tail', new TextEncoder().encode(prefix).length)).toBe(prefix.length);
});

it('treats a multiline end column of zero as exclusive', () => {
  const location: sourceLocation = {fileId: 'f', startLine: 1, endLine: 2, startColumn: 1, endColumn: 0};
  expect(lineRange('first', 1, location)).toEqual([1, 5]);
  expect(lineRange('second', 2, location)).toBeNull();
});

it('highlights the exact Unicode range in original CRLF source', () => {
  const text = '\treturn "😀 café"';
  const project: pyProject = {projectID: 'p', projectName: 'Demo', files: [
    {fileID: 'f', fileName: 'main.py', filePath: 'app/main.py', fileContent: `def f():\r\n${text}\r\n`},
  ]};
  const startColumn = new TextEncoder().encode('\treturn "').length;
  const endColumn = new TextEncoder().encode('\treturn "😀 café').length;
  const {container} = render(<ProjectViewer project={project} selectedFileId="f" onSelectFile={vi.fn()}
    highlight={{fileId: 'f', startLine: 2, endLine: 2, startColumn, endColumn}} />);
  expect(container.querySelector('mark')?.textContent).toBe('😀 café');
  expect(container.querySelectorAll('.fileCodeLine').length).toBe(3);
});

it('selects duplicate basenames by file ID and displays full paths', () => {
  const project: pyProject = {projectID: 'p', projectName: 'Demo', files: [
    {fileID: 'a', fileName: 'main.py', filePath: 'app/main.py', fileContent: 'one'},
    {fileID: 'b', fileName: 'main.py', filePath: 'tests/main.py', fileContent: 'two'},
  ]};
  const selected = vi.fn();
  render(<ProjectViewer project={project} selectedFileId="a" highlight={null} onSelectFile={selected} />);
  fireEvent.click(screen.getByRole('button', {name: 'tests/main.py'}));
  expect(selected).toHaveBeenCalledWith(project.files[1]);
});
