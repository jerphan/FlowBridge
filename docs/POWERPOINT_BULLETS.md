# Code Manager presentation bullets

Presenter: Justin Bean

## Slide 1 - My module: Code Manager

- Implemented Python file uploads, nested ZIP imports, and public GitHub imports.
- Organized original source into `PyProject` and `SourceFile` models with UUIDs and relative paths.
- Provided one consistent input contract for the parser and original-source retrieval.

## Slide 2 - How the module works

- FastAPI routes call the import service, which shares source-decoding and archive-reading logic.
- Preserved indentation, comments, line endings, and duplicate filenames in different folders.
- Validated paths, encodings, sizes, and GitHub requests; failed imports keep earlier projects available.

## Slide 3 - Verification and team handoff

- Passed 229 backend/integration cases, 284 parser cases, 16 UI cases, and six browser flow checks.
- Used FastAPI and pytest from the proposed backend stack, with working project/file retrieval endpoints.
- Connected imports to parsing, diagrams, source highlights, and SVG exports. Intended-user validation remains NOT RUN.

The automated test count is the verified result for this implementation snapshot.
If the code changes, rerun tests and update these bullets with the new actual result.
