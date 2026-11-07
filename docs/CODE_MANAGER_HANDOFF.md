# Code Manager handoff

Module owner: Justin Bean

Project: FlowBridge / The Adaptables

## Quick walkthrough

Read these files in this order:

1. `models.py`: `SourceFile` holds one file; `PyProject` groups the files. Pydantic
   checks the fields when a model is created or read from JSON.
2. `service.py`: `loadFile`, `loadZip`, and `loadGit` build a new project. They
   return its file list; `getProject()` returns the complete project.
3. `readers.py`: reads the original source and checks ZIP paths and size limits.
   `github.py` downloads a repository ZIP for this same reader.
4. `api.py`: accepts UI requests and calls the manager. `registry.py` keeps
   successful imports available for later project and file requests.
5. `pipeline.py`: passes the saved project to Harsha's parser and returns matching
   graph and source-mapping output.

A manager holds one current project. A failed import leaves that project alone.
The API gives each import its own manager, then saves the result in the shared
registry. That registry is temporary memory and clears when the server stops.

Use `fileID` for file lookup and `filePath` to distinguish files such as
`app/main.py` and `tests/main.py`. The camelCase names match the team's shared
JSON and UML contract. The parser receives `fileContent` as the original decoded
text; this module does not analyze or run it.

## Implemented contribution

Justin's Code Manager module now provides the shared source/project models,
binary source decoding, bounded Python/ZIP acquisition, public GitHub archive
imports, original-source lookups, a FastAPI adapter, a capacity-limited in-memory
registry, automated tests, runnable demonstrations, and integration documentation.

The original `CodeManager.py` was an unfinished model scaffold with no working
loaders or backend. It now re-exports the implemented package so existing imports
and the proposed UML class names have one canonical implementation. The team's
existing static frontend files are unchanged.

## Responsibilities and files

| File | Responsibility |
| --- | --- |
| `FlowBridgeBackend/models.py` | Shared Pydantic v2 `SourceFile` and `PyProject` contract |
| `FlowBridgeBackend/service.py` | `CodeManager`, atomic replacement imports and lookup |
| `FlowBridgeBackend/readers.py` | Bounded reads, original-source decoding, ZIP validation |
| `FlowBridgeBackend/paths.py` | Safe names and normalized relative paths |
| `FlowBridgeBackend/github.py` | GitHub URL validation, metadata, redirects, bounded download |
| `FlowBridgeBackend/config.py` | Import, GitHub timeout, and registry configuration |
| `FlowBridgeBackend/registry.py` | Locked application-owned project snapshots and source access |
| `FlowBridgeBackend/api.py` | FastAPI routes, dependency injection, error handling, CORS |
| `FlowBridgeBackend/pipeline.py` | Code Manager to parser handoff and matching consumer outputs |
| `FlowBridgeBackend/source_mapping.py` | Graph/node source lookups for one project and its current revision |
| `flowbridge/`, `CodeManager.py` | Original import names pointing to the current backend |
| `FlowBridgeBackend/cli.py` | File/ZIP/GitHub import demonstration, real project JSON |
| `tests/` | Offline automated model, loader, GitHub, API, registry, and CLI tests |
| `examples/sample_project/` | Three nested Python files with duplicate basenames |
| `scripts/smoke_api.py` | Real localhost HTTP/server startup demonstration |
| `pyproject.toml`, `uv.lock` | Python 3.12 baseline, reproducible dependency workflow |

Code Manager owns source acquisition and retrieval. Parsing, graph construction,
and source locations come from the separate Parsing & Analysis package through
the pipeline below. Authentication, diagram layout/rendering, and highlighting
are outside Code Manager.
No uploaded modules are imported, executed, or installed. Python syntax errors are
preserved as text for the parser. Input decoding errors are handled here.

## Stack and setup

The Stage 2 slides recommend FastAPI and pytest for the Python backend; both are
used here. Pydantic v2 defines the shared models and HTTPX handles GitHub requests.
React, React Flow, and Vitest belong to the UI/diagram work. SQLite is the proposed
persistence option; this demo uses the in-memory registry requested by the module
specification.

Use Python 3.12 and uv from the repository root:

```powershell
uv sync --locked
uv run uvicorn FlowBridgeBackend.api:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs`. Use one server worker; each process has a
separate in-memory registry. Restarting clears saved projects.

Public GitHub imports work without a token. An optional token can be set before
starting the backend:

```powershell
$env:GITHUB_TOKEN = "your-token"
```

Do not commit tokens. The backend reads the process environment and does not
automatically load a `.env` file.

## Terminal demos and checks

```powershell
uv run pytest -q --cov=flowbridge --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .

uv run flowbridge-code file examples/sample_project/app/main.py
uv run python -c "import shutil; shutil.make_archive('demo-project', 'zip', 'examples/sample_project')"
uv run flowbridge-code zip demo-project.zip --project-name "Nested demo"

# Optional live import; requires internet and is separate from the automated tests.
uv run flowbridge-code github https://github.com/jerphan/FlowBridge

# Starts and stops a real local server; makes no GitHub requests.
uv run python scripts/smoke_api.py
```

`uv run python -m flowbridge file <path.py>` is an equivalent CLI entry point.
The CLI opens supplied local files; the HTTP API accepts uploads. Project JSON
goes to stdout. Import errors go to stderr with exit code 1.

## Public service API

```python
from typing import BinaryIO
from flowbridge import CodeManager, PyProject, SourceFile, pyProject, sourceFile
from flowbridge.config import GitHubSettings, ImportLimits

manager = CodeManager(
    limits=ImportLimits(),
    github_settings=GitHubSettings(),  # Omitting this reads optional GITHUB_TOKEN.
    github_client=None,  # Optional caller-owned httpx.AsyncClient.
)

# Signatures (file is an already-open binary stream):
# loadFile(file: BinaryIO, *, fileName: str, projectName: str | None = None) -> list[SourceFile]
# loadZip(file: BinaryIO, *, fileName: str, projectName: str | None = None) -> list[SourceFile]
# loadGit(url: str, *, projectName: str | None = None) -> list[SourceFile]
# getProject() -> PyProject
# getSourceFile(fileID: str) -> SourceFile
# getSourceFileByPath(filePath: str) -> SourceFile

with open("examples/sample_project/app/main.py", "rb") as stream:
    files = manager.loadFile(stream, fileName="main.py")
project = manager.getProject()
original = manager.getSourceFile(files[0].fileID)
```

`manager.project` is the single canonical current project; it is initially `None`.
Every successful loader returns a list and replaces that project. Every loader
constructs and validates a complete candidate before assigning it. Any failed
eligible Python file rejects the whole import and leaves the prior project and
its IDs intact. Imports never implicitly append to the current project.

These loaders are synchronous. FastAPI's synchronous handlers run them in worker
threads. Other asynchronous callers must similarly offload them; do not call the
synchronous GitHub loader directly from an already-running event loop. GitHub
network operations use an internal async HTTPX client and `asyncio.timeout` to
enforce the total network deadline. Owned clients close after each import;
injected clients must be closed by their owner and used within a compatible event
loop lifecycle. Injecting MockTransport clients is supported by the tests.

One manager belongs to one project context. Its mutable current-project state is
not a shared concurrent-request store. The API creates a new manager per import.

## Models and serialization

| Model | Exact Python and JSON fields |
| --- | --- |
| `PyProject` | `projectID: str`, `projectName: str`, `files: list[SourceFile]` |
| `SourceFile` | `fileID: str`, `fileName: str`, `filePath: str`, `fileContent: str` |

Names and casing match the requested contract. `fileName` is the basename;
`filePath` is project-relative with forward slashes. `app/main.py` and
`tests/main.py` are separate files even though their basenames match.

`SourceFile` is frozen to protect original content and identity. `PyProject`
identity/display fields are also frozen; use `project.addFile(file)` when building
a project, rather than changing its `files` list directly. `addFile` rejects
duplicate IDs or normalized paths. Deserialization validates those same rules.
Lookups scan the model contents and do not rely on private serialized indexes.

```python
encoded = project.model_dump_json(indent=2)
restored = PyProject.model_validate_json(encoded)
as_dict = project.model_dump()
from_dict = PyProject.model_validate(as_dict)

restored.getFileByID(original.fileID)
restored.getFileID(original.fileID)  # UML compatibility wrapper; returns SourceFile.
```

Only shared model fields serialize. IDs are UUID strings created at file/project
creation. They remain stable during lookup, repeated downstream reuse, and JSON
round trips. A fresh import, even of identical input, creates fresh IDs. Default
display names are the single Python filename stem, ZIP filename stem, or canonical
GitHub repository name. An override is trimmed and must be nonblank.

See the [HTTP contract](#http-contract) for the exact payload.

## HTTP contract

| Route | Input | Success |
| --- | --- | --- |
| `POST /api/projects/file` | Multipart `file`, optional `projectName` | 201, project JSON |
| `POST /api/projects/zip` | Multipart `file`, optional `projectName` | 201, project JSON |
| `POST /api/projects/github` | JSON `url`, optional `projectName` | 201, project JSON |
| `GET /api/projects/{projectID}` | Project ID | 200, project JSON |
| `GET /api/projects/{projectID}/files/{fileID}` | Both IDs | 200, original SourceFile JSON |
| `GET /health` | None | 200, health JSON |
| `POST /api/projects/{projectID}/analyze` | Project ID, optional `revisionId` query parameter | 200, analysis plus flowchart and mapping JSON |
| `GET /api/projects/{projectID}/flowchart` | Project ID, optional `revisionId` query parameter | 200, flowchart JSON |
| `GET /api/projects/{projectID}/mapping` | Project ID, optional `revisionId` query parameter | 200, source-mapping JSON |
| `GET /api/projects/{projectID}/source-location` | Required `graphId` and `nodeId` query parameters, optional `revisionId` | 200, project/revision IDs, location, original file |

The import response is the project itself:

```json
{
  "projectID": "9d2e8c32-9480-4e32-9aaf-27149b1dfe87",
  "projectName": "StudentProject",
  "files": [
    {
      "fileID": "8f54f2df-6bb9-4a7e-b62c-940be0ec924b",
      "fileName": "main.py",
      "filePath": "app/main.py",
      "fileContent": "print('hello')\n"
    }
  ]
}
```

These IDs are illustrative. Each fresh import creates new UUIDs; keep the returned
IDs when calling the parser or retrieving original source. Errors use the shape
documented in the [error contract](#error-contract).

## Source, path, and archive policy

- Read bytes with bounded calls; detect encoding with `tokenize.detect_encoding`;
  decode strictly. UTF-8, a UTF-8 BOM, and Python encoding declarations such as
  Latin-1 are supported. Unknown/conflicting declarations, invalid byte sequences,
  non-text codecs, and decoded lone surrogates produce an encoding error.
- Preserve decoded tabs, spaces, comments, blank lines, LF/CRLF/mixed endings,
  missing or present final newlines, and empty Python files. Do not reconstruct
  tokens or parse syntax. The transport BOM and original encoding bytes are not
  retained in the decoded-source contract.
- Accept `.py` case-insensitively and preserve filename/path case. A single upload
  discards browser directory prefixes (including `C:\fakepath\`) and uses its safe
  basename as `filePath`. The API never opens that filename on the server.
- Read ZIP entries in memory without extracting them. Recurse through archive
  paths and sort eligible Python files by normalized `filePath`. User ZIPs retain
  every folder component; no guessed common root is removed.
- Check every ZIP entry path before filtering extensions or excluded directories.
  Reject absolute, drive-prefixed, UNC, parent-traversal, NUL/control-character,
  and colon-containing paths. The extra control/colon restriction provides a
  portable relative-path contract. Remove `.` components and repeated separators
  only after checking unsafe components; normalize backslashes to `/`.
- Reject duplicate normalized archive paths, even when they are non-Python
  entries. Matching is case-sensitive. Distinct case spellings remain distinct.
- Skip `.git`, `.venv`, `venv`, `__pycache__`, `node_modules`, and `__MACOSX`
  directory components (configurable, exact case). Do not read excluded contents,
  nested ZIPs, or ordinary non-Python files.
- Reject eligible symlinks/special files, eligible encrypted files, unreadable or
  corrupt selected data, unsupported selected compression, and archives without
  eligible Python files. An error never commits a partial project.
- Inspect archive entry count and total declared uncompressed bytes before reading
  selected entries. Check per-source and project metadata budgets, and enforce
  actual source bytes while reading/decompressing selected entries.

## GitHub policy

Accept only repository-root HTTPS links at exactly `github.com`, optionally with
a trailing slash or `.git`. Reject credentials, any explicit port, query strings,
fragments, SSH links, arbitrary hosts, and `/tree/` or `/blob/` links.

Read metadata from the constructed GitHub API URL, confirm the repository is
public, use its actual default branch, and download its REST ZIP archive. Follow
at most three redirects across HTTPS `api.github.com` / `codeload.github.com`;
metadata redirects stay on the API host. Build fresh request headers for each hop.
Send the optional token only to `api.github.com`, never to the archive host, and
never print it. Client-level auth/cookies/query parameters are not inherited.

Strip only the known GitHub-generated `owner-repository-<commit hash>/` wrapper,
validated against canonical repository metadata. All paths underneath remain
unchanged. Process the result using the same ZIP/source reader as uploads.

Finite defaults: 5 seconds to connect, 15 seconds of read inactivity, and 60 seconds
for the overall GitHub operation. The deadline cancels slow network streaming;
the service also checks elapsed time after bounded ZIP/source processing before
committing. Metadata responses are limited to 1 MiB. Archive downloads are bounded
with and without `Content-Length`. There are no retry loops.

This version imports the default branch only. It does not fetch submodules,
Git LFS objects, private repositories, selected subfolders, or arbitrary branch
URLs, and it never clones or executes repository code.

## Demo limits and application storage

| Limit | Default |
| --- | --- |
| One Python source file (original input bytes) | 1 MiB |
| Uploaded/downloaded compressed archive | 20 MiB |
| Eligible Python source bytes per project | 20 MiB |
| Total declared uncompressed archive bytes, including ignored entries | 50 MiB |
| Archive entries | 10,000 |
| Eligible Python files | 1,000 |
| Retained projects | 10 |
| Retained decoded source, measured as UTF-8 bytes | 100 MiB |

Configure these with `ImportLimits`, `GitHubSettings`, `RegistryLimits`, and
`create_app(...)`. These are the demo's supported import sizes; there is no claim
to support arbitrarily large repositories.

The app registry stores validated source snapshots keyed by `projectID`. Capacity
checking and registration share a lock, so concurrent imports cannot overfill it.
Registration rejects a full registry with HTTP 503 before storing the candidate;
previous projects remain accessible. Snapshot copies prevent later caller changes
from changing retained source or bypassing byte accounting. File retrieval requires
both a project context and its file ID. Shutdown clears the registry; a restart
loses all projects. There is no database, eviction policy, or deletion endpoint.

Use a single server worker for the demo. Production deployment needs shared
durable storage plus explicit HTTP request-body, multipart, timeout, concurrency,
and rate limits at the server/proxy layer. A bounded `UploadFile.file` read does
not bound every byte of an incoming multipart body; multipart parsing occurs
before the route loader runs. CORS is an origin policy, not authentication.

## Error contract

```json
{"error":{"code":"INVALID_SOURCE_ENCODING","message":"Python source has an unknown, conflicting, or invalid encoding.","filePath":"app/main.py"}}
```

No original source, tokens, upstream response bodies, server-local upload paths,
or stack traces are included in these public errors. The module does not log
source contents or credentials. Error file paths, when present, have already
passed the relative-path policy.

| Code | HTTP | Meaning |
| --- | --- | --- |
| `INVALID_INPUT` | 400 | Wrong upload type/name, blank display name, invalid stream/path |
| `INVALID_REQUEST` | 400 | Missing/malformed FastAPI request fields or JSON |
| `INVALID_ARCHIVE` | 400 | Corrupt/unsafe/unsupported selected ZIP data |
| `INVALID_SOURCE_ENCODING` | 400 | Source cannot be decoded/represented under the contract |
| `DUPLICATE_FILE` | 400 | Duplicate file ID/path or duplicate project registration |
| `INVALID_GITHUB_URL` | 400 | URL is not a supported repository root |
| `NO_PROJECT_LOADED` | 404 | Service used before its first successful import |
| `PROJECT_NOT_FOUND` | 404 | Project not retained in this app instance |
| `FILE_NOT_FOUND` | 404 | File not in the specified project |
| `SOURCE_MAPPING_NOT_FOUND` | 404 | Node has no source range in the selected project/revision |
| `IMPORT_LIMIT_EXCEEDED` | 413 | Configured size/count budget exceeded |
| `NO_PYTHON_FILES` | 422 | Empty repository/archive or no eligible Python files |
| `GITHUB_RATE_LIMITED` | 429 | Upstream primary/secondary rate-limit response |
| `GITHUB_UNAVAILABLE` | 502 | Missing/private/inaccessible repository, failed network/upstream response |
| `INVALID_GITHUB_REDIRECT` | 502 | Unsafe/malformed/missing/excessive redirect |
| `REGISTRY_CAPACITY_EXCEEDED` | 503 | Demo registry is full |
| `GITHUB_TIMEOUT` | 504 | Read/connect timeout or overall deadline exceeded |
| `HTTP_ERROR` | Original HTTP status | Framework-level HTTP error, such as unknown route |

Model-construction/deserialization errors use Pydantic `ValidationError` in Python;
`PyProject.addFile` and missing lookups use the documented domain exceptions.

## UI integration

Import endpoints return the project itself. Save its `projectID` and each `fileID`.
Read errors from `body.error.message`; use `body.error.code` for UI behavior.
Do not manually set multipart `Content-Type`; the browser supplies its boundary.

```javascript
const form = new FormData();
form.append("file", selectedFile);
form.append("projectName", "My project"); // Optional; omit when no override is wanted.
const route = selectedFile.name.toLowerCase().endsWith(".zip") ? "zip" : "file";
const response = await fetch(`http://127.0.0.1:8000/api/projects/${route}`, {
  method: "POST", body: form
});
const body = await response.json();
if (!response.ok) throw new Error(body.error.message);
const project = body;

// Alternative public repository input:
const imported = await fetch("http://127.0.0.1:8000/api/projects/github", {
  method: "POST", headers: {"Content-Type": "application/json"},
  body: JSON.stringify({url: repositoryUrl})
});
```

New backend defaults allow local UI origins on ports 5173 and 3000 for localhost
and 127.0.0.1. Set `create_app(cors_origins=("https://actual-ui-origin",))` when
integrating another origin. The React/Vite frontend is in `FlowBridgeFrontend/`.
Its file/ZIP requests use these routes, but the current app still displays a
placeholder diagram and an embedded editor. The file-view component must be
mounted and the Start button must call analysis.

## Parser and source-mapping handoff

`FlowBridgePipeline` connects the existing manager to Harsha's analysis package.
Code Manager's source-reading methods and the parser's algorithms remain separate.

```python
from FlowBridgeBackend import FlowBridgePipeline

result = FlowBridgePipeline(manager).analyze_current(revision_id=1)
flowchart = result["flowchart"]
mapping = result["mapping"]
```

The pipeline serializes the complete project, normalizes `projectID`/`fileID` to
the parser's `projectId`/`fileId`, and analyzes once before creating both output
projections. Identity values, relative paths, and original text stay unchanged.
The full response also includes `analysis`, `status`, `projectId`, `projectName`,
and `revisionId`.

Use `POST /api/projects/{projectID}/analyze` when both outputs are needed.
The separate flowchart/mapping GET routes are conveniences that reanalyze the
same saved snapshot. Pair results only when project and revision IDs match.

The optional `revisionId` query parameter defaults to 1 and must be nonnegative;
invalid values return the existing HTTP 400 `INVALID_REQUEST` response. This
version imports immutable source snapshots. If editing is added, the coordinating
backend must allocate a new revision before analyzing changed text and the UI
must discard stale responses. The adapter does not assign revisions or keep a counter.

Python syntax errors become analysis diagnostics and a partial result; they do
not overwrite original source. Unsupported features also produce explicit statuses
and diagnostics. See the parser's [integration guide](../FlowBridge_ParsingAndAnalysis/docs/INTEGRATION_GUIDE.md)
and [supported subset](../FlowBridge_ParsingAndAnalysis/docs/PARSING_FEATURES.md).

Grace's Source Mapping Layer loads the pipeline's `mapping` output, finds a node
using both `graphId` and `nodeId`, and returns its location:

```python
from FlowBridgeBackend.source_mapping import SourceMappingLayer

layer = SourceMappingLayer(projectId=result["projectId"])
layer.loadMappingOutput(result["mapping"])
location = layer.getSourceLocation(graph_id, node_id)
if location is not None:
    original = registry.getSourceFile(result["projectId"], location.fileId)
```

Use one layer per project. Full mapping outputs require `projectId`, a nonnegative
integer `revisionId`, and `sourceMappings`. Older revisions and another project's
output are rejected. Invalid or duplicate entries leave the previous mappings
intact. `updateMappings(list)` is the lower-level replacement method; revision
checks belong to `loadMappingOutput`.

For the browser, `GET /api/projects/{projectID}/source-location` accepts `graphId`,
`nodeId`, and optional `revisionId` query parameters. It reanalyzes the saved
snapshot, uses the layer, and returns:

```javascript
{
  projectId, revisionId,
  location: { fileId, startLine, endLine, startColumn, endColumn },
  file: { fileID, fileName, filePath, fileContent }
}
```

`location.fileId` equals `file.fileID`; the different ID spellings follow the two
existing contracts. `getSourceLocation` returns `None` for an unmapped node. The
HTTP route returns 404 `SOURCE_MAPPING_NOT_FOUND`, including for synthetic Start/End
nodes and graph IDs from another revision. Original-file retrieval is also
available independently at `GET /api/projects/{projectID}/files/{fileID}`.

Mapping locations use one-based lines, zero-based UTF-8 byte columns, and
exclusive end positions. Convert those columns to the editor's coordinates
before highlighting; JavaScript string indexes are not UTF-8 byte offsets.
Selecting nodes and applying highlights remain UI/connection-management work.

## UML revisions

- Add `SourceFile.filePath: String` to preserve nested and duplicate-basename files.
- Use `PyProject` and `SourceFile` consistently; lowercase UML aliases refer to the
  same classes. Retain `projectName` as a display label.
- All loaders return `List<SourceFile>`; each also commits one complete project.
- Use `getSourceFile(fileID)` / `getFileByID(fileID)` for identity lookup and the
  explicit `getSourceFileByPath(filePath)` for path lookup.
- Clarify that the legacy `getFileID(fileID)` returns a `SourceFile` object.
- Place the parser call in an application coordinator after successful import;
  the source acquisition service stays independent of parsing.
- Show the application registry with project-scoped source retrieval and atomic
  capacity registration. See the matching `.mmd` sources in `docs/diagrams/`.

## Remaining team integration work

1. Finish UI input/state: add public GitHub input, mount the file viewer, surface
   upload errors, and send the optional project name as `projectName`.
2. Connect Start to analysis and retain matching project/revision outputs.
3. Implement Diagram Manager layout, interactive rendering, view navigation, and export.
4. Connect node clicks to source lookup, display the returned original file, and
   convert UTF-8 byte columns before highlighting in the editor.
5. Run browser integration tests once upload → diagram → node click → source
   highlight works. Backend integration tests can run now.
6. Conduct intended-user validation and record actual observations/feedback.

The current single-worker demo uses in-memory storage. Persistence and any
authentication needed beyond that demo remain separate scope decisions.

No unfinished placeholder logic remains in the Code Manager import/retrieval
module. External module integration and intended-user validation remain separate
team work. See `VALIDATION.md` for actual checks, technical notes, and NOT RUN rows.

## Implementation references

- [GitHub repository archive endpoint](https://docs.github.com/en/rest/repos/contents#download-a-repository-archive-zip): archive redirects and empty-repository behavior.
- [Python 3.12 source encoding detection](https://docs.python.org/3.12/library/tokenize.html#tokenize.detect_encoding): BOM/encoding-cookie handling.
- [HTTPX timeout documentation](https://www.python-httpx.org/advanced/timeouts/): connect/read inactivity budgets; the overall deadline is separately enforced.
- [FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/): binary `UploadFile.file` and multipart inputs.
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/): validation and model serialization.
