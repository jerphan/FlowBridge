from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from FlowBridgeBackend.api import create_app
from FlowBridgeBackend.diagram_renderer.organizer import GraphOrganizer
from FlowBridgeBackend.diagram_renderer.runner import HierarchicalDiagramPipeline


@pytest.fixture
def export_client(tmp_path):
    app = create_app(render_root=tmp_path)
    with TestClient(app) as client:
        yield client


def imported_file(client, source=b"def check():\n    return 1\n", name="Demo"):
    response = client.post(
        "/api/projects/file", files={"file": ("main.py", source)}, data={"projectName": name}
    )
    assert response.status_code == 201
    return response.json()


def test_render_payload_and_original_source_lookup_agree(export_client):
    source = 'message = "café 😀"\r\n'.encode()
    project = imported_file(export_client, source)
    url = f"/api/projects/{project['projectID']}"
    response = export_client.post(url + "/render")
    assert response.status_code == 200
    rendered = response.json()
    assert rendered["analysisStatus"] == rendered["status"] == "success"
    assert set(rendered["graphs"]) == set(rendered["flowchart"]["graphs"])
    file_graph = next(g for g in rendered["flowchart"]["graphs"].values() if g["graphType"] == "file")
    node = next(n for n in file_graph["nodes"] if n["sourceLocation"])
    indexed = rendered["sourceMapping"]["nodes"][node["nodeId"]]
    original = export_client.get(url + "/source-location", params={
        "graphId": file_graph["graphId"], "nodeId": node["nodeId"],
    })
    assert original.status_code == 200
    selected = original.json()
    assert selected["location"] == node["sourceLocation"]
    assert indexed["span"]["fileId"] == selected["file"]["fileID"]
    assert indexed["span"]["filePath"] == selected["file"]["filePath"]
    assert selected["file"]["fileContent"].encode() == source
    assert all('onclick=' not in graph["svg"] for graph in rendered["graphs"].values())
    assert export_client.post(url + "/render").json() == rendered


def test_duplicate_basenames_and_function_names_have_distinct_exports(export_client, make_zip):
    source = b"def check():\n    return 1\ndef check():\n    return 2\n"
    project = export_client.post(
        "/api/projects/zip",
        files={
            "file": (
                "project.zip",
                make_zip(
                    [
                        ("app/main.py", source),
                        ("tests/main.py", source),
                    ]
                ),
            )
        },
    ).json()
    response = export_client.post(
        f"/api/projects/{project['projectID']}/render", params={"revisionId": 0}
    )
    assert response.status_code == 200
    rendered = response.json()
    assert rendered["projectId"] == project["projectID"]
    assert rendered["revisionId"] == 0
    assert rendered["status"] == "success"
    viewer = export_client.get(rendered["viewerUrl"])
    assert viewer.status_code == 200
    manifest = export_client.get(rendered["manifestUrl"]).json()
    assert manifest["projectId"] == project["projectID"]
    assert manifest["revisionId"] == 0
    exports = manifest["graphs"]
    assert len(exports) == 7  # project, two files, four separate function definitions
    assert len({entry["path"] for entry in exports}) == 7
    assert {entry.get("filePath") for entry in exports} >= {"app/main.py", "tests/main.py"}
    for entry in exports:
        svg = export_client.get(rendered["viewerUrl"] + entry["path"])
        assert svg.status_code == 200
        assert ElementTree.fromstring(svg.content).tag.endswith("svg")


def test_projects_and_revisions_keep_separate_viewers(export_client):
    first = imported_file(export_client, name="First project")
    second = imported_file(export_client, name="Second project")
    responses = [
        export_client.post(
            f"/api/projects/{project['projectID']}/render", params={"revisionId": revision}
        ).json()
        for project, revision in [(first, 1), (second, 1), (first, 2)]
    ]
    assert len({response["viewerUrl"] for response in responses}) == 3
    for response, title in zip(
        responses, ["First project", "Second project", "First project"], strict=True
    ):
        assert title in export_client.get(response["viewerUrl"]).text
    assert "Second project" not in export_client.get(responses[0]["viewerUrl"]).text


def test_failed_export_leaves_existing_viewer_and_source_intact(export_client):
    first = imported_file(export_client)
    base = f"/api/projects/{first['projectID']}"
    original = export_client.post(base + "/render").json()
    html = export_client.get(original["viewerUrl"]).text
    second = imported_file(export_client, name="Second")
    with patch.object(
        HierarchicalDiagramPipeline, "run", side_effect=OSError("private disk details")
    ):
        failed = export_client.post(f"/api/projects/{second['projectID']}/render")
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "DIAGRAM_RENDER_FAILED"
    assert "private disk" not in failed.text
    assert export_client.get(original["viewerUrl"]).text == html
    assert export_client.get(base).json() == first
    assert export_client.get(f"/viewer/{second['projectID']}/1/").status_code == 404


@pytest.mark.parametrize("revision", [-1, "invalid", "1.5"])
def test_export_rejects_invalid_revisions(export_client, revision):
    response = export_client.post("/api/projects/missing/render", params={"revisionId": revision})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_export_looks_up_project_and_preserves_partial_status(export_client):
    missing = export_client.post("/api/projects/missing/render")
    assert missing.status_code == 404
    project = imported_file(export_client, b"def broken(:\n")
    response = export_client.post(f"/api/projects/{project['projectID']}/render")
    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert export_client.get(response.json()["viewerUrl"]).status_code == 200


def test_viewer_keeps_uploaded_names_and_code_as_text(export_client):
    name = "</script><script>window.exportInjected = true</script>"
    project = imported_file(export_client, b'value = "<img src=x onerror=alert(1)>"\n', name)
    response = export_client.post(f"/api/projects/{project['projectID']}/render").json()
    viewer = export_client.get(response["viewerUrl"]).text
    assert viewer.count("<script>") == 1
    assert name not in viewer
    assert "\\u003c/script\\u003e" in viewer


def test_shutdown_removes_only_the_apps_temporary_exports(tmp_path):
    app = create_app(render_root=tmp_path)
    workspace = Path(app.state.render_workspace.name)
    with TestClient(app) as client:
        project = imported_file(client)
        assert client.post(f"/api/projects/{project['projectID']}/render").status_code == 200
        assert workspace.is_dir()
    assert not workspace.exists()
    assert tmp_path.is_dir()


def test_renderer_navigation_uses_graph_and_node_ids_together():
    model = GraphOrganizer().organize(
        {
            "projectId": "p",
            "projectName": "P",
            "graphs": {},
            "graphReferences": [
                {"sourceGraphId": "one", "sourceNodeId": "shared", "targetGraphId": "target1"},
                {"sourceGraphId": "two", "sourceNodeId": "shared", "targetGraphId": "target2"},
            ],
        }
    )
    assert model.node_to_child_graph[("one", "shared")] == "target1"
    assert model.node_to_child_graph[("two", "shared")] == "target2"
