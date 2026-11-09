# Module handoff

## Source contract

Every import returns the same Pydantic `PyProject`:

```json
{"projectID":"UUID","projectName":"Demo","files":[{"fileID":"UUID","fileName":"main.py","filePath":"app/main.py","fileContent":"value = 1\n"}]}
```

Basenames and relative paths are separate so duplicate filenames are safe.
Content is original decoded text with indentation and line endings preserved.
`pyProject`/`sourceFile` are aliases to the same classes.

`CodeManager.loadFile/loadZip/loadGit` return source-file lists;
`getProject` returns the project. File lookup uses IDs or relative paths.
Each API import gets a request-local manager. Only successful imports publish
a validated snapshot to the shared, thread-safe registry.

GitHub import validates a public repository root URL, reads GitHub metadata for
the default branch, follows validated archive redirects, and uses the same ZIP
reader as uploads. Readers detect Python encodings, collect nested Python files,
exclude dependency folders and reject unsafe archive entries. Syntax errors
reach the parser as original source.

The registry retains recent projects within count/UTF-8-byte limits. A new valid
snapshot can expire least-recently used ones. A snapshot larger than the entire
budget is rejected before anything is removed.

## HTTP routes

| Route | Input/result |
| --- | --- |
| `GET /health` | Server health |
| `POST /api/projects/file` | Multipart `file`, optional `projectName` |
| `POST /api/projects/zip` | Multipart ZIP `file`, optional `projectName` |
| `POST /api/projects/github` | JSON `url`, optional `projectName` |
| `GET /api/projects/{projectID}` | Original project |
| `GET /api/projects/{projectID}/files/{fileID}` | Original file JSON |
| `POST /api/projects/{projectID}/analyze` | Analysis, flowchart, mapping |
| `GET /api/projects/{projectID}/flowchart` | Diagram data |
| `GET /api/projects/{projectID}/mapping` | Canonical mappings |
| `GET /api/projects/{projectID}/source-location` | Original file/range for graph/node IDs |
| `GET /api/projects/{projectID}/display` | Display-only comment/docstring ranges |
| `POST /api/projects/{projectID}/render` | SVG interface payload, diagnostics, export URLs |

Analysis/render/lookup use a nonnegative `revisionId`, default 1. Source lookup
also needs `graphId` and `nodeId`. Unknown/expired IDs return 404.
Errors use `{"error":{"code":"...","message":"..."}}`.
[Interactive API documentation](http://localhost:8000/docs) is available locally.

Defaults: 1 MiB per source file; 20 MiB archive/collected source; 50 MiB total
uncompressed content; 1,000 Python files; 10,000 archive entries. The registry
keeps at most 10 projects and 100 MiB source text. Configuration lives in `config.py`.

## Analysis and source mapping

`FlowBridgePipeline` maps Code Manager's uppercase ID keys to the parser's
`projectId/fileId` and adds the caller's revision. Both consumer projections
come from one canonical result. See [PARSER.md](PARSER.md).

Mappings use the graph/node tuple, one-based lines, and zero-based UTF-8 byte
columns with an exclusive end. Synthetic nodes may have no range.
The UI highlights whole original lines. Comment filtering uses tokenizer/AST
locations, preserves hashes inside strings, and never rewrites or renumbers source.

## UI and exports

`UploadModal` handles all imports. `App` owns project/request identity,
cancellation and navigation. `FlowchartCanvas` displays SVGs and pan/zoom.
`SourceCodeViewer` connects lines and nodes. `WorkspaceDialog` provides
settings/session information. `ExportModal` saves the selected diagram.

Old requests cannot replace new projects. Failed imports preserve the current
workspace. Files are selected by ID and displayed with relative paths.
Requests have a finite timeout and can be retried.

Render returns project/revision/status, graph SVGs/dimensions, canonical flowchart,
navigation/source indexes, diagnostics, file statuses and viewer/manifest URLs.
Always use returned URLs. Exports are temporary, application/project/revision
scoped, and publish together. Duplicate files/functions have distinct paths.
Existing generated viewers remain available until the application shuts down.

PNG export refuses unsafe canvas dimensions and offers SVG instead. PDF pages
match the diagram size so tall diagrams start on page one without A4 shrink-to-fit.
Generated diagrams/results are ignored by Git. No account or database is used.
