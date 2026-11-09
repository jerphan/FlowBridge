import type {SourceLocation} from './types/flowchart';
import {utf8ColumnIndex} from './sourceRange';

export function filterSourceLine(text: string, line: number, ranges: SourceLocation[]): string | null {
  const pieces = ranges.filter(range => range.startLine <= line && range.endLine >= line)
    .map(range => [range.startLine === line ? utf8ColumnIndex(text, range.startColumn) : 0,
      range.endLine === line ? utf8ColumnIndex(text, range.endColumn) : text.length])
    .sort((a, b) => b[0] - a[0]);
  let displayed = text;
  for (const [start, end] of pieces) displayed = displayed.slice(0, start) + displayed.slice(end);
  return pieces.length && !displayed.trim() ? null : displayed;
}
