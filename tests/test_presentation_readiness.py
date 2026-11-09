import io
import math
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from FlowBridgeBackend.api import create_app
from FlowBridgeBackend.diagram_renderer.layout import SugiyamaDAGLayout


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(render_root=tmp_path)) as http:
        yield http


def import_file(client, source, name="main.py"):
    response = client.post("/api/projects/file", files={"file": (name, source.encode())})
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize("source,status", [
    ("", "success"),
    ('message = "café 😀"\r\n', "success"),
    ("def pick(value):\n    if value:\n        return 1\n    return 0\n", "success"),
    ("while True:\n    break\nelse:\n    unused = 1\n", "success"),
    ("def run():\n    try:\n        return 1\n    finally:\n        cleanup = 2\nrun()\n", "success"),
    ("def broken(:\n", "partial"),
    ("class Example:\n    pass\n", "partial"),
    ("async def run():\n    return 1\n", "partial"),
    ("if True:\n    return 1\n", "partial"),
])
def test_demo_inputs_render_without_losing_source(client, source, status):
    project = import_file(client, source)
    base = f"/api/projects/{project['projectID']}"
    response = client.post(base + "/render")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == payload["analysisStatus"] == status
    assert payload["projectId"] == project["projectID"]
    assert client.get(payload["viewerUrl"]).status_code == 200
    for graph in payload["graphs"].values():
        assert ElementTree.fromstring(graph["svg"]).tag.endswith("svg")
    original = client.get(base + "/files/" + project["files"][0]["fileID"]).json()
    assert original["fileContent"] == source


def test_small_source_cannot_expand_into_an_unbounded_diagram(client):
    source = "def f0():\n    return 1\n"
    for index in range(1, 14):
        source += f"def f{index}():\n    f{index - 1}()\n    f{index - 1}()\n"
    source += "f13()\n"
    project = import_file(client, source)
    response = client.post(f"/api/projects/{project['projectID']}/render")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "partial"
    assert any(d["code"] == "CFG_LIMIT" for d in result["diagnostics"])
    file = result["analysisFiles"][0]
    graph = result["flowchart"]["graphs"][file["graphId"]]
    assert graph["status"] == "failed"
    assert graph["nodes"] == []


def test_rendering_never_executes_uploaded_source(client, tmp_path):
    marker = tmp_path / "must-not-exist.txt"
    project = import_file(client, f"open({str(marker)!r}, 'w').write('executed')\n")
    response = client.post(f"/api/projects/{project['projectID']}/render")
    assert response.status_code == 200
    assert not marker.exists()


def test_simultaneous_renders_publish_one_complete_snapshot(client):
    project = import_file(client, "value = 1\n")
    url = f"/api/projects/{project['projectID']}/render"
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(url), range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    manifest = client.get(responses[0].json()["manifestUrl"]).json()
    assert all(client.get(responses[0].json()["viewerUrl"] + entry["path"]).status_code == 200
               for entry in manifest["graphs"])


def test_circular_imports_keep_both_files_and_their_views(client):
    archive = io.BytesIO()
    with ZipFile(archive, "w") as files:
        files.writestr("a.py", "from b import second\ndef first():\n    return second()\n")
        files.writestr("b.py", "from a import first\ndef second():\n    return first()\n")
    project = client.post("/api/projects/zip", files={"file": ("cycle.zip", archive.getvalue())}).json()
    response = client.post(f"/api/projects/{project['projectID']}/render")
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "success"
    assert len(result["analysisFiles"]) == 2
    assert set(result["graphs"]) == set(result["flowchart"]["graphs"])


@pytest.mark.parametrize("source", [
    "def run(v):\n    for n in range(4):\n        if n % 2:\n            continue\n        else:\n            break\n    else:\n        done = 1\nrun(3)\n",
    "def run(v):\n    while True:\n        try:\n            break\n        finally:\n            cleanup = 1\nrun(3)\n",
    "def run(v):\n    if v > 2:\n        return 1\n    elif v < 0:\n        return -1\n    else:\n        return 0\nrun(3)\n",
    "def run(v):\n    try:\n        try:\n            raise ValueError()\n        except TypeError:\n            return 1\n    except ValueError:\n        return 2\n    finally:\n        cleanup = 3\nrun(3)\n",
    "def helper():\n    return 1\ndef run(v):\n    try:\n        return helper()\n    finally:\n        cleanup = 2\nrun(3)\n",
    "def run(v):\n    try:\n        work()\n" + "".join(f"    except Error{index}:\n        handled = {index}\n" for index in range(9)) + "run(3)\n",
    'def run(v):\n    message = "' + "long_label_" * 25 + '"\n    return message\nrun(3)\n',
])
def test_layouts_keep_every_edge_inside_the_svg(client, source):
    project = import_file(client, source)
    result = client.get(f"/api/projects/{project['projectID']}/flowchart").json()
    assert result["status"] == "success"
    for graph in result["graphs"].values():
        laid_out = SugiyamaDAGLayout().layout(graph, "Presentation", {})
        assert {edge.edge_id for edge in laid_out.edges} == {edge["edgeId"] for edge in graph["edges"]}
        assert math.isfinite(laid_out.width) and math.isfinite(laid_out.height)
        for edge in laid_out.edges:
            assert all(math.isfinite(x) and math.isfinite(y)
                       and 0 <= x <= laid_out.width and 0 <= y <= laid_out.height for x, y in edge.points)
        for node in laid_out.nodes:
            assert 0 <= node.x <= laid_out.width - node.width
            assert 0 <= node.y <= laid_out.height - node.height


def test_true_and_false_edges_leave_different_ports(client):
    project = import_file(client, "def run(value):\n    if value:\n        return 1\n    return 0\n")
    result = client.get(f"/api/projects/{project['projectID']}/flowchart").json()
    graph = next(g for g in result["graphs"].values() if g["graphType"] == "function")
    layout = SugiyamaDAGLayout().layout(graph, "Branches", {})
    branches = [edge for edge in layout.edges if edge.edge_type in ("true", "false")]
    assert len(branches) == 2
    assert branches[0].points[0] != branches[1].points[0]
