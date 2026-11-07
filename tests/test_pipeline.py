import httpx
import pytest
from fastapi.testclient import TestClient

from FlowBridgeBackend.api import create_app
from FlowBridgeBackend.config import GitHubSettings


@pytest.mark.parametrize("kind", ["file", "zip", "github"])
@pytest.mark.parametrize("revision", [0, 7])
def test_import_analysis_and_original_source_handoff(kind, revision, make_zip, mock_client):
    sources = [
        (
            "app/main.py",
            b"def add(a, b):\r\n\treturn a + b\r\n\r\ntotal: int = 0\r\n"
            b"for number in range(3):\r\n\ttotal += add(number, 1)\r\nelse:\r\n\tprint(total)\r\n",
        ),
        ("tests/main.py", b'# coding: latin-1\r\ndef greeting():\r\n    return "caf\xe9"\r\n'),
    ]
    github_zip = make_zip([(f"owner-repo-abcdef1/{path}", text) for path, text in sources])

    def github_request(request):
        if request.url.path == "/repos/owner/repo":
            return httpx.Response(
                200,
                json={
                    "private": False,
                    "default_branch": "main",
                    "owner": {"login": "owner"},
                    "name": "repo",
                },
            )
        if request.url.host == "api.github.com":
            return httpx.Response(
                302, headers={"location": "https://codeload.github.com/owner/repo/zip/main"}
            )
        return httpx.Response(200, content=github_zip)

    app = create_app(
        github_client=mock_client(github_request), github_settings=GitHubSettings(token=None)
    )
    with TestClient(app) as client:
        if kind == "github":
            response = client.post(
                "/api/projects/github", json={"url": "https://github.com/owner/repo"}
            )
        elif kind == "zip":
            response = client.post(
                "/api/projects/zip", files={"file": ("project.zip", make_zip(sources))}
            )
        else:
            response = client.post("/api/projects/file", files={"file": ("main.py", sources[0][1])})
        assert response.status_code == 201
        project = response.json()
        project_url = f"/api/projects/{project['projectID']}"
        analyzed = client.post(f"{project_url}/analyze", params={"revisionId": revision})
        assert analyzed.status_code == 200
        result = analyzed.json()
        assert result["status"] == "success"
        assert result["projectId"] == project["projectID"]
        assert result["revisionId"] == revision
        assert result["flowchart"]["revisionId"] == result["mapping"]["revisionId"] == revision
        graphs = result["flowchart"]["graphs"]
        assert {graph["graphType"] for graph in graphs.values()} >= {"function", "module"}
        for reference in result["flowchart"]["graphReferences"]:
            assert reference["targetGraphId"] in graphs
        call = next(
            call
            for call in result["analysis"]["callReferences"]
            if call["expression"] == "add(number, 1)"
        )
        assert call["resolution"] == "resolved"
        assert call["targetGraphId"] in graphs
        assert (
            client.get(f"{project_url}/flowchart", params={"revisionId": revision}).json()
            == result["flowchart"]
        )
        assert (
            client.get(f"{project_url}/mapping", params={"revisionId": revision}).json()
            == result["mapping"]
        )

        originals = {file["fileID"]: file for file in project["files"]}
        assert {file["fileId"] for file in result["analysis"]["files"]} == set(originals)
        assert len(originals) == (1 if kind == "file" else 2)
        for mapping in result["mapping"]["sourceMappings"]:
            file_id = mapping["location"]["fileId"]
            assert client.get(f"{project_url}/files/{file_id}").json() == originals[file_id]
            selected = client.get(
                f"{project_url}/source-location",
                params={
                    "graphId": mapping["graphId"],
                    "nodeId": mapping["nodeId"],
                    "revisionId": revision,
                },
            )
            assert selected.status_code == 200
            assert selected.json() == {
                "projectId": project["projectID"],
                "revisionId": revision,
                "location": mapping["location"],
                "file": originals[file_id],
            }
        expected = {path: content for path, content in sources}
        for file in originals.values():
            raw = sources[0][1] if kind == "file" else expected[file["filePath"]]
            encoding = "latin-1" if file["filePath"] == "tests/main.py" else "utf-8"
            assert file["fileContent"] == raw.decode(encoding)


@pytest.mark.parametrize(
    "route,method",
    [
        ("analyze", "post"),
        ("flowchart", "get"),
        ("mapping", "get"),
        ("source-location", "get"),
    ],
)
@pytest.mark.parametrize("revision", ["-1", "invalid", "1.5"])
def test_invalid_analysis_revisions_return_input_errors(route, method, revision):
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        project = client.post(
            "/api/projects/file", files={"file": ("main.py", b"def f():\n    pass\n")}
        ).json()
        response = getattr(client, method)(
            f"/api/projects/{project['projectID']}/{route}",
            params={"revisionId": revision, "graphId": "g", "nodeId": "n"},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_source_selection_uses_original_unicode_byte_columns_and_context():
    source = 'def greeting():\r\n\treturn "café"\r\n'
    with TestClient(create_app()) as client:
        project = client.post(
            "/api/projects/file", files={"file": ("main.py", source.encode("utf-8"))}
        ).json()
        url = f"/api/projects/{project['projectID']}"
        analyzed = client.post(f"{url}/analyze", params={"revisionId": 7}).json()
        entry = next(
            entry
            for entry in analyzed["mapping"]["sourceMappings"]
            if entry["location"]["startLine"] == 2
        )
        params = {"graphId": entry["graphId"], "nodeId": entry["nodeId"], "revisionId": 7}
        selected = client.get(f"{url}/source-location", params=params)
        assert selected.status_code == 200
        assert selected.json()["file"] == project["files"][0]
        location = selected.json()["location"]
        assert location == entry["location"]
        encoded_line = source.splitlines()[1].encode("utf-8")
        assert (
            encoded_line[location["startColumn"] : location["endColumn"]]
            == 'return "café"'.encode()
        )

        for bad_params in [{**params, "nodeId": "missing"}, {**params, "revisionId": 8}]:
            missing = client.get(f"{url}/source-location", params=bad_params)
            assert missing.status_code == 404
            assert missing.json()["error"]["code"] == "SOURCE_MAPPING_NOT_FOUND"
        synthetic_nodes = [
            (graph["graphId"], node["nodeId"])
            for graph in analyzed["flowchart"]["graphs"].values()
            if graph["graphType"] == "function"
            for node in graph["nodes"]
            if node["sourceLocation"] is None
        ]
        assert len(synthetic_nodes) >= 2
        for graph_id, node_id in synthetic_nodes:
            synthetic = client.get(
                f"{url}/source-location",
                params={
                    **params,
                    "graphId": graph_id,
                    "nodeId": node_id,
                },
            )
            assert synthetic.status_code == 404
            assert synthetic.json()["error"]["code"] == "SOURCE_MAPPING_NOT_FOUND"
        other = client.post("/api/projects/file", files={"file": ("other.py", b"x = 2\n")}).json()
        assert (
            client.get(
                f"/api/projects/{other['projectID']}/source-location", params=params
            ).status_code
            == 404
        )
        unknown = client.get("/api/projects/missing/source-location", params=params)
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "PROJECT_NOT_FOUND"
        assert client.get(f"{url}/source-location").status_code == 400


@pytest.mark.parametrize("source", ["if True:\n    return 1\n", "for x in [1]:\n    return x\n"])
def test_invalid_module_control_flow_returns_partial_analysis(source):
    with TestClient(create_app()) as client:
        project = client.post(
            "/api/projects/file", files={"file": ("main.py", source.encode())}
        ).json()
        response = client.post(f"/api/projects/{project['projectID']}/analyze")
        assert response.status_code == 200
        assert response.json()["status"] == "partial"
        assert any(
            d["code"] == "UNSUPPORTED_FEATURE" for d in response.json()["analysis"]["diagnostics"]
        )


def test_invalid_python_produces_diagnostics_without_losing_original_source():
    with TestClient(create_app()) as client:
        first = client.post(
            "/api/projects/file", files={"file": ("main.py", b"def f():\n    pass\n")}
        ).json()
        broken = client.post(
            "/api/projects/file", files={"file": ("broken.py", b"def broken(:\r\n")}
        ).json()
        response = client.post(f"/api/projects/{broken['projectID']}/analyze")
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "partial"
        assert any(item["code"] == "SYNTAX_ERROR" for item in result["analysis"]["diagnostics"])
        assert client.get(f"/api/projects/{first['projectID']}").json() == first
        file = broken["files"][0]
        assert (
            client.get(f"/api/projects/{broken['projectID']}/files/{file['fileID']}").json()[
                "fileContent"
            ]
            == "def broken(:\r\n"
        )
