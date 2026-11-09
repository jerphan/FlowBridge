"""Locate display-only comments without changing stored source or analysis."""

import ast
import io
import tokenize

from .models import SourceFile, SourceLocation


def comment_ranges(file: SourceFile) -> list[SourceLocation]:
    lines = file.fileContent.splitlines(keepends=True)
    ranges = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(file.fileContent).readline):
            if token.type == tokenize.COMMENT:
                start_line, start_column = token.start
                end_line, end_column = token.end
                ranges.append(SourceLocation(
                    fileId=file.fileID, startLine=start_line, endLine=end_line,
                    startColumn=len(lines[start_line - 1][:start_column].encode("utf-8")),
                    endColumn=len(lines[end_line - 1][:end_column].encode("utf-8")),
                ))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # Valid tokens still help display an incomplete file; the parser owns diagnostics.

    try:
        tree = ast.parse(file.fileContent)
    except (SyntaxError, ValueError, RecursionError):
        return ranges
    for owner in ast.walk(tree):
        if not isinstance(owner, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if not owner.body:
            continue
        first = owner.body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            ranges.append(SourceLocation(
                fileId=file.fileID, startLine=first.lineno, endLine=first.end_lineno,
                startColumn=first.col_offset, endColumn=first.end_col_offset,
            ))
    return ranges
