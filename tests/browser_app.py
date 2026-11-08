"""Offline GitHub fixture for the browser check; not the production app."""

import io
import os
import zipfile
from pathlib import Path

import httpx
from fastapi.responses import Response

from FlowBridgeBackend.api import create_app
from FlowBridgeBackend.config import GitHubSettings

archive = io.BytesIO()
with zipfile.ZipFile(archive, "w") as files:
    sources = {
        "helper.py": b"def adjust(value):\r\n    if value > 0:\r\n        return value + 1\r\n    return 0\r\n",
        "app/main.py": 'from helper import adjust\r\nanswer = adjust(2)\r\nmessage = "café 😀"\r\n'.encode(),
        "tools/main.py": b"def tool():\n    return 2\n",
        "README.md": b"Only Python files should be imported.",
    }
    for name, source in sources.items():
        files.writestr(f"demo-repo-abcdef1/{name}", source)


def github_request(request):
    if request.url.path == "/repos/demo/repo":
        return httpx.Response(
            200,
            json={
                "private": False,
                "default_branch": "main",
                "owner": {"login": "demo"},
                "name": "repo",
            },
        )
    if request.url.path == "/repos/demo/missing":
        return httpx.Response(404)
    if request.url.host == "api.github.com":
        return httpx.Response(
            302, headers={"location": "https://codeload.github.com/demo/repo/zip/main"}
        )
    return httpx.Response(200, content=archive.getvalue())


app = create_app(
    github_settings=GitHubSettings(token=None),
    github_client=httpx.AsyncClient(transport=httpx.MockTransport(github_request)),
    cors_origins=("http://127.0.0.1:5188",),
    render_root=Path(os.environ["FLOWBRIDGE_E2E_OUTPUT_DIR"]),
)


@app.get("/_browser_fixture")
def fixture_ready():
    return {"fixture": "flowbridge-browser-check"}


@app.get("/_browser_fixture/archive.zip")
def fixture_archive():
    return Response(archive.getvalue(), media_type="application/zip")
