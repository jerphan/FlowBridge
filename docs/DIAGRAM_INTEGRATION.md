# Diagram and UI integration

React Flow is the application's main diagram interface. Harsha's SVG renderer is
the export path. Both consume the same parser graph IDs and source mappings;
neither executes uploaded code. Existing Code Manager acquisition and Grace's
SourceMappingLayer are unchanged.

## Components

| File | Responsibility |
| --- | --- |
| `FlowBridgeFrontend/src/api.ts` | Shared API URL and user-facing request errors |
| `components/GitHubUploader.tsx` | Native dialog, controlled URL, JSON import request, cancellation/errors |
| `components/FileUploader.tsx` | Python/ZIP multipart requests with optional `projectName` |
| `components/StartButton.tsx` | Analyze the current project and reject stale/mismatched responses |
| `diagram.ts` | Dagre layout and graph-to-React-Flow node/edge conversion |
| `components/DiagramManager.tsx` | All four graph types, Back/view selection, node lookup and drill-down |
| `sourceRange.ts`, `components/ProjectViewer.tsx` | Original source display and UTF-8-byte to JavaScript-index highlighting |
| `components/ExportButton.tsx` | Request exports and expose the returned viewer link |
| `FlowBridgeBackend/diagram_renderer/` | SVG layout, export manifest, and standalone viewer |

Frontend paths in this table are relative to `FlowBridgeFrontend/src/` unless stated otherwise.

## Request flow

1. Imports return one `PyProject`; failed imports leave the current UI project intact.
   GitHub requests send `{ "url": "https://github.com/owner/repo" }`, with an optional
   `projectName`. Python/ZIP requests send multipart `file` and optional `projectName`.
2. Start calls `GET /api/projects/{projectID}/flowchart?revisionId=1`. Project and
   revision identity must match before the UI accepts the response.
3. Diagram Manager renders actual `nodes` and `edges` from the selected graph.
   `edgeId`, `sourceId`, and `targetId` are preserved; labels such as true/false,
   return, back, and imports remain visible. View selection covers project, file,
   module, and function graphs. Failed/unsupported views display their status.
4. A source-backed node calls `/source-location` with its graph/node IDs and
   current revision. The returned original file becomes the source selection.
   Python lines are one-based; columns are zero-based UTF-8 bytes with an exclusive
   end. The UI converts these to UTF-16 string indexes, including emoji/Unicode.
5. Double-click navigation follows `graphReferences` using the graph/node tuple.
   Synthetic Start/End nodes have no source range. Project file nodes can open
   their child graph directly.

The parser's new file CFG includes bounded same-file call expansion. Expansion
requires a resolved CallReference: shadowed or unresolved calls remain atomic.
`return other_function()` terminates its caller after expansion. Failed initial
file analysis is not reused by file-view construction. A later file-view failure
has an empty failed file graph while valid function/sibling views remain available.

## SVG exports

`POST /api/projects/{projectID}/render?revisionId=1` returns:

```json
{
  "projectId": "returned project ID",
  "revisionId": 1,
  "status": "success",
  "fileCount": 3,
  "viewerUrl": "/viewer/project-id/1/",
  "manifestUrl": "/viewer/project-id/1/manifest.json"
}
```

Use the actual returned URLs. Output is isolated per application, project, and
revision. Completed exports publish together; an export failure cannot replace
another project's viewer. The viewer route exists even without checked-in
generated diagrams. Exports are temporary and are removed when the app shuts down.

Physical SVG filenames use file/function list positions, not uploaded basenames.
This preserves `app/main.py` and `tests/main.py`, including duplicate function
names. `manifest.json` maps every exported graph ID to its path and status, keeping
the original file path as metadata. The viewer supports navigation and SVG downloads.
Uploaded names/code remain text in SVG/HTML; embedded viewer data escapes script
delimiters and breadcrumbs use DOM text nodes.

## Run and test

From the repository root, `uv sync --locked` then run the backend on port 8000.
From `FlowBridgeFrontend`, `npm ci` then `npm run dev` uses the default API URL.
Set `VITE_API_BASE_URL` before starting/building for a different API. Configure the
backend's `cors_origins` when using a different UI origin.

`uv run python scripts/check_modules.py` runs backend pytest and parser unittest
suites. `npm test` checks forms, cancellation/stale responses, layout, duplicate
paths, and Unicode highlighting. `npm run build` checks TypeScript and Vite.

For the browser check, run `npx playwright install chromium`, then `npm run test:browser`.
It starts an isolated API on 8877 and UI on 5188, uses the real API with mocked
GitHub archive responses, and checks GitHub/file/ZIP imports, edges, navigation,
source highlights, failed imports, and SVG download/isolation. Those ports must
be free. Browser results/failure screenshots go to ignored `test-results/`.

The check uses the root `.venv` Python by default. `FLOWBRIDGE_PYTHON` can point to
another interpreter with the locked project installed. `FLOWBRIDGE_BROWSER_EXECUTABLE`
can point to an installed Chromium browser instead of downloading Playwright's browser.

## Boundaries

The existing supported Python subset still applies; this is not runtime execution
or complete Python name/exception analysis. Source snapshots and the registry are
in memory. Editing with new revision allocation, saved workspaces/authentication,
and intended-user validation remain separate work. Generated dependencies,
bytecode, browser results, and diagram output are ignored by Git.
