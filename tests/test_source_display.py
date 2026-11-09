from fastapi.testclient import TestClient

from FlowBridgeBackend.api import create_app
from FlowBridgeBackend.models import SourceFile
from FlowBridgeBackend.source_display import comment_ranges


def source(text):
    return SourceFile(fileName="main.py", filePath="main.py", fileContent=text)


def test_hashes_inside_strings_are_preserved_and_columns_use_utf8():
    text = 'message = "😀 # keep"  # hide\n'
    ranges = comment_ranges(source(text))
    assert len(ranges) == 1
    assert ranges[0].startColumn == len(text[:text.index("# hide")].encode())
    assert ranges[0].endLine == 1


def test_docstrings_are_identified_without_hiding_assigned_multiline_strings():
    text = ('"""Module documentation."""\n'
            'message = """Keep this string."""\n'
            'def run():\n    """Function documentation.\n    Second line."""\n    return message\n')
    ranges = comment_ranges(source(text))
    assert [(span.startLine, span.endLine) for span in ranges] == [(1, 1), (4, 5)]


def test_comments_in_an_incomplete_file_do_not_break_display():
    ranges = comment_ranges(source("def broken(:\n    # still a comment\n"))
    assert any(span.startLine == 2 for span in ranges)


def test_display_metadata_does_not_modify_original_content(tmp_path):
    text = '# heading\r\nmessage = "# keep"  # hide\r\n'
    with TestClient(create_app(render_root=tmp_path)) as client:
        project = client.post("/api/projects/file", files={"file": ("main.py", text.encode())}).json()
        base = f"/api/projects/{project['projectID']}"
        display = client.get(base + "/display")
        assert display.status_code == 200
        assert display.json()["projectId"] == project["projectID"]
        assert len(display.json()["files"][project["files"][0]["fileID"]]) == 2
        assert client.get(base).json() == project
        assert client.get(base + "/files/" + project["files"][0]["fileID"]).json()["fileContent"] == text
