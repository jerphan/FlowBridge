# Diagram and UI integration

The application keeps Harsha's final SVG canvas, hierarchical layout, upload
modal, diagnostic panels, breadcrumbs and export modal. The backend connects
these to Code Manager and preserves Grace's source-location API.

## Components

| Component | Responsibility |
| --- | --- |
| `components/UploadModal.tsx` | Python/ZIP multipart requests and GitHub URL JSON requests; errors and cancellation |
| `App.tsx` | Current project, rendering request, file identity, graph navigation and stale-response checks |
| `components/StartButton.tsx` | Start generation and indicate its pending state |
| `components/FlowchartCanvas.tsx` | Display SVGs, pan/zoom, graph-node clicks and highlights |
| `components/SourceCodeViewer.tsx` | Display original decoded source and paths; connect source lines to graph nodes |
| `components/ExportModal.tsx` | Download selected SVG/PNG or open a PDF print page |
| `FlowBridgeBackend/api.py` | Import, analysis, original-source lookup and isolated render endpoints |
| `FlowBridgeBackend/source_mapping.py` | Grace's canonical graph/node-to-source lookup |
| `FlowBridgeBackend/SourceMapping/` | Derived node/line index used by the SVG interface |
| `FlowBridgeBackend/diagram_renderer/` | Layout, SVG generation, manifest and standalone viewer |

Frontend component paths are relative to `FlowBridgeFrontend/src/`.
Earlier React Flow components remain available for compatibility; the main
application uses the final SVG interface.

## Request flow

1. Python, ZIP and GitHub imports return the same `PyProject`. File IDs, relative
   paths and original decoded source remain unchanged. Only Python source files
   are collected; parsing support is a separate stage.
2. GitHub sends `{ "url": "https://github.com/owner/repo" }`, with optional
   `projectName`. Python/ZIP uploads send multipart `file` and `projectName`.
   A failed or dismissed import does not replace the current project.
3. Start sends `POST /api/projects/{projectID}/render?revisionId=1`. The pipeline
   analyzes the snapshot, lays out the graphs, creates SVGs and derives a source
   index. Uploaded Python is never executed.
4. The response includes `projectId`, `revisionId`, `status`, `projectName`,
   `projectGraphId`, `graphs`, `flowchart`, `sourceMapping`, navigation indexes,
   `diagnostics`, `analysisFiles`, `analysisStatus`, `viewerUrl` and
   `manifestUrl`. Each `graphs` entry has its ID, type, title, SVG and dimensions.
   Backend module graphs remain available in the response alongside file views.
5. Linked node clicks open file/function graphs; statement clicks highlight source
   lines. Source-line clicks highlight a mapped node. File selection uses file IDs;
   full relative paths distinguish files with identical basenames.
6. Importing another project cancels the pending render. Responses must match the
   current request, project ID and revision before they update the screen.

The existing `/analyze`, `/flowchart`, `/mapping`, original-file and
`/source-location` routes remain available. Source lookup accepts the project,
revision, graph ID and node ID, and returns the original file and source range.
Python lines are one-based; columns are zero-based UTF-8 bytes with an exclusive
end. The current SVG interface highlights whole source lines. Canonical mappings
and graph references continue to identify nodes by their owning graph and node.

## Parser behavior

File views retain bounded same-file call expansion. Only resolved calls can be
expanded; shadowed calls remain atomic. Returning an expanded call ends its caller
before following statements. Function-view calls retain the final branch's
clickable function nodes and graph references.

Try/except/else/finally and explicit raise are supported within the procedural
subset. Cleanup runs before outgoing returns, exceptions, breaks and continues.
Separate cleanup copies retain separate continuations; cleanup may override an
earlier transfer. Nested unmatched exceptions reach enclosing handlers. Exception
edges are conservative possible paths, not inferred runtime exception types.

Direct relative package imports use the existing static resolver and are no
longer rejected by feature validation. Star, future, conditional/local and dynamic
imports retain their documented restrictions.

Initial CFG failures discard that file's partial state and keep valid siblings.
Later file-view failures produce an empty failed file graph while retaining valid
function graphs. Analysis diagnostics and partial status are preserved.

## Saved exports

Use the returned `viewerUrl` and `manifestUrl`. Each application owns a temporary
export directory; project and revision subdirectories prevent overwriting another
project. A completed render and its response publish together and are immutable
for that project/revision. Shutdown removes the temporary exports.

Physical filenames use file/function positions. Duplicate basenames and repeated
function names therefore produce distinct SVGs. The manifest records graph IDs,
original relative paths and statuses. Generated diagrams are ignored by Git.

SVGs use data attributes for navigation. React attaches its own click handlers;
the standalone viewer delegates clicks to those attributes. Uploaded names and
code remain text, including in viewer breadcrumbs and PDF titles.

## Run and test

From the root: `uv sync --locked`, then
`uv run uvicorn FlowBridgeBackend.api:app --host 127.0.0.1 --port 8000`.
From `FlowBridgeFrontend`: `npm ci` and `npm run dev`.
`VITE_API_BASE_URL` overrides the default API URL. Other UI origins require the
matching backend `cors_origins`.

Run `uv run python scripts/check_modules.py`, `npm test`, and `npm run build`.
For real-browser checks, install Chromium with `npx playwright install chromium`,
then run `npm run test:browser`. It starts an isolated API on 8877 and UI on 5188
and exercises 13 scenarios with offline GitHub metadata/archive fixtures.
Those ports must be free. Results go to ignored `test-results/`.

The browser check uses the root `.venv` by default. `FLOWBRIDGE_PYTHON` can select
another installed environment, and `FLOWBRIDGE_BROWSER_EXECUTABLE` can select an
installed Chromium browser. PDF checking verifies the print page and headless
rendering; the native operating-system print dialog is not automated.

Source snapshots remain in memory. Editing, saved workspaces, accounts and full
Python runtime semantics are outside this integration. See `VALIDATION.md` for
executed checks and the distinction between automated checks and user validation.
