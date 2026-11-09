# Demo verification

Verified November 9, 2026, on Windows with Python 3.12.14 and Node 22.17.1.
This combines the final parser/interface integration with Harsha's November 8
diagram-routing and project-selection changes (`73e96e3`).

## Executed checks

| Check | Result |
| --- | --- |
| Backend pytest | 264 passed; no failures, errors or skips |
| Parser unittest | 301 passed |
| Frontend Vitest | 33 passed |
| Production TypeScript/Vite build | Passed |
| Real browser with production UI and local API | 29 scenarios passed; no page JavaScript errors |
| Repeated ZIP imports | 24 sequential archives containing 10 Python files each, then 4 concurrent imports; imports returned 201, recent projects and health remained usable, expired IDs returned 404 |
| PDF exports | File and tall function exports each contain one populated page with Start/End text; first-page renders visually inspected |
| Live public GitHub import | HTTP 201; 8 Python files; successful analysis with 17 graphs, no diagnostics; original-file retrieval 200 |
| Team's complex test ZIP | 15 Python files; render/viewer/display/health succeeded; 46 graphs; partial analysis with explicit unsupported-class and conservative-analysis diagnostics |
| Ruff and dependency lock | Passed for integration files; `uv lock --check` passed |
| Source/wheel build | Passed |
| Fresh installed wheel outside checkout | API import, display metadata, file edges, source lookup, SVG/viewer export, duplicate-path isolation and CLI startup passed |

The unit/integration suites contain **598 tests**, separate from the 29 browser
scenarios. Browser tests use the real application API with deterministic GitHub
responses; the separate live import uses the actual public demo repository.
The native operating-system print dialog was not automated. Browser-generated
PDFs verify the print document, page sizing and diagram content.

## Regressions covered

- File, ZIP and public GitHub imports share the source contract; nested paths,
  duplicate basenames, encodings, indentation, line endings and original content
  survive the handoff. Uploaded code is never executed.
- Invalid archives, unsafe paths, oversized inputs, failed GitHub requests,
  rate limits, timeouts and retries produce errors while preserving valid data.
- Retained projects obey count/UTF-8-byte limits with least-recently used expiry.
  Invalid snapshots and individually oversized snapshots do not remove old data.
- Finally cleanup after terminal transfers, relative imports, shadowed functions,
  unreachable code, bounded recursion/expansion and failed-file isolation have
  regression coverage. Oversized graph expansion produces CFG_LIMIT diagnostics.
- Nodes, edges, loop/branch/exception routing, drill-down, bidirectional source
  highlighting, project revisions and the original source-location route work
  through the combined pipeline.
- Selection uses file identity. Old renders cannot replace newer projects.
  Synthetic/unmapped selections clear previous highlights; source clicks prefer
  the narrowest matching range in the active graph.
- Canvas fitting completes before the first paint, preventing a delayed viewport
  change during node clicks. Selection remains highlighted through zoom and pan.
- Settings and workspace buttons open working panels. Comment/docstring filtering
  preserves string literals, original source, UTF-8 ranges and original line numbers.
- Start New Project clears the view and opens import, including during a pending
  render. Late responses stay ignored. The avatar's focus outline stays inside
  its 44-pixel button, and header actions fit all three tested viewports.
- SVG/PNG/PDF export, duplicate export names, publication isolation, unsupported
  views, large-PNG fallback and application-shutdown cleanup are checked.
- Browser checks include 1280x720, 1366x768 and 1920x1080 viewports, failed imports,
  cleared-server-session recovery, and the repeated ZIP scenario above.

## Reproduce

From the repository root:

```powershell
uv sync --locked
uv run python scripts/check_modules.py
uv run ruff check CodeManager.py FlowBridgeBackend flowbridge scripts tests
uv lock --check
uv build
cd FlowBridgeFrontend
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:browser
```

The browser runner uses isolated ports 5188/8877 and cleans up its processes.
Its ignored `test-results` directory contains the report, screenshot and PDFs.
Set `FLOWBRIDGE_PYTHON` or `FLOWBRIDGE_BROWSER_EXECUTABLE` to use existing runtimes.
GitHub Actions repeats module, frontend, browser, lint, build and wheel checks.

## Demo scope

Use one backend worker. Project storage is temporary; restarting clears it.
No sign-in or database is included, as agreed for the presentation. The old
"storage is full" error was the configured project limit, not a missing database.
New valid imports now release inactive snapshots automatically.

This is static analysis of the documented Python subset, not execution or complete
Python semantics. Unsupported classes/async and resource limits appear as
diagnostics; do not present them as fully analyzed code. See [PARSER.md](PARSER.md).
The complex fixture intentionally includes unsupported classes, so partial status
is expected. Keep a local ZIP available for GitHub outages or rate limits.

No intended-user study was conducted or claimed in these developer checks.
Cloudflare deployment is maintained separately. The existing HTTPX/Starlette
TestClient deprecation warning is non-failing. Historical plans and audits are
preserved in Git history and the [notes archive](archive/previous-project-notes.zip).
