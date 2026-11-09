import type {sourceLocation} from './types/types';

// Python uses UTF-8 byte columns; JavaScript slices use UTF-16 string indexes.
export function utf8ColumnIndex(text: string, column: number): number {
  const encoder = new TextEncoder();
  let bytes = 0;
  let index = 0;
  for (const character of text) {
    const length = encoder.encode(character).length;
    if (bytes + length > column) break;
    bytes += length;
    index += character.length;
  }
  return index;
}

export function lineRange(text: string, line: number, location: sourceLocation): [number, number] | null {
  if (line < location.startLine || line > location.endLine) return null;
  if (line === location.endLine && location.endColumn === 0 && line > location.startLine) return null;
  const start = line === location.startLine ? utf8ColumnIndex(text, location.startColumn) : 0;
  const end = line === location.endLine ? utf8ColumnIndex(text, location.endColumn) : text.length;
  return [start, end];
}
