from copy import deepcopy
from dataclasses import asdict

import pytest

from FlowBridgeBackend.models import SourceLocation, SourceMapping
from FlowBridgeBackend.source_mapping import SourceMappingLayer


@pytest.fixture
def mapping_output():
    return {
        "projectId": "p001",
        "revisionId": 2,
        "sourceMappings": [
            {
                "graphId": "g_fn_check",
                "nodeId": "c_condition",
                "location": {
                    "fileId": "f002",
                    "startLine": 2,
                    "endLine": 2,
                    "startColumn": 7,
                    "endColumn": 18,
                },
            },
            {
                "graphId": "g_other",
                "nodeId": "c_condition",
                "location": {
                    "fileId": "f003",
                    "startLine": 3,
                    "endLine": 4,
                    "startColumn": 8,
                    "endColumn": 0,
                },
            },
        ],
    }


def test_lookup_uses_both_graph_and_node_ids(mapping_output):
    layer = SourceMappingLayer()
    layer.loadMappingOutput(mapping_output)
    assert (layer.projectId, layer.revisionId) == ("p001", 2)
    for entry in mapping_output["sourceMappings"]:
        assert asdict(layer.findSourceMapping(entry["graphId"], entry["nodeId"])) == entry
        assert (
            asdict(layer.getSourceLocation(entry["graphId"], entry["nodeId"])) == entry["location"]
        )
    assert layer.findSourceMapping("unknown", "c_condition") is None
    assert layer.getSourceLocation("g_fn_check", "unknown") is None


@pytest.mark.parametrize(
    "bad_entry",
    [
        {},
        None,
        {"graphId": "g", "nodeId": "n", "location": {}},
        {"graphId": "g", "nodeId": "n", "location": None},
    ],
)
def test_failed_update_preserves_complete_previous_output(mapping_output, bad_entry):
    layer = SourceMappingLayer()
    layer.loadMappingOutput(mapping_output)
    layer.selectedGraphId = "g_fn_check"
    layer.selectedNodeId = "c_condition"
    replacement = deepcopy(mapping_output)
    replacement["revisionId"] = 3
    replacement["sourceMappings"].append(bad_entry)
    with pytest.raises(ValueError):
        layer.loadMappingOutput(replacement)
    assert [asdict(entry) for entry in layer.sourceMappings] == mapping_output["sourceMappings"]
    assert (layer.projectId, layer.revisionId) == ("p001", 2)
    assert (layer.selectedGraphId, layer.selectedNodeId) == ("g_fn_check", "c_condition")


@pytest.mark.parametrize(
    "field,value",
    [
        ("projectId", "other"),
        ("projectId", ""),
        ("revisionId", 1),
        ("revisionId", -1),
        ("revisionId", True),
        ("revisionId", "3"),
        ("sourceMappings", None),
    ],
)
def test_wrong_context_or_revision_does_not_replace_mappings(mapping_output, field, value):
    layer = SourceMappingLayer(projectId="p001")
    layer.loadMappingOutput(mapping_output)
    replacement = deepcopy(mapping_output)
    replacement[field] = value
    with pytest.raises(ValueError):
        layer.loadMappingOutput(replacement)
    assert layer.revisionId == 2
    assert [asdict(entry) for entry in layer.sourceMappings] == mapping_output["sourceMappings"]


def test_requires_mapping_output_and_all_metadata(mapping_output):
    for invalid in [
        None,
        {"mapping": mapping_output},
        {key: value for key, value in mapping_output.items() if key != "revisionId"},
        {key: value for key, value in mapping_output.items() if key != "sourceMappings"},
    ]:
        layer = SourceMappingLayer()
        with pytest.raises(ValueError):
            layer.loadMappingOutput(invalid)
        assert layer.sourceMappings == []
        assert (layer.projectId, layer.revisionId) == (None, None)


def test_reload_and_empty_new_revision_clear_selection(mapping_output):
    layer = SourceMappingLayer()
    layer.loadMappingOutput(mapping_output)
    layer.loadMappingOutput(mapping_output)
    assert len(layer.sourceMappings) == 2
    layer.selectedNodeId = "c_condition"
    layer.selectedGraphId = "g_fn_check"
    layer.loadMappingOutput({**mapping_output, "revisionId": 3, "sourceMappings": []})
    assert layer.sourceMappings == []
    assert layer.revisionId == 3
    assert (layer.selectedGraphId, layer.selectedNodeId) == (None, None)
    other = SourceMappingLayer()
    other.loadMappingOutput({**mapping_output, "projectId": "other", "revisionId": 0})
    assert (other.projectId, other.revisionId) == ("other", 0)


def test_duplicate_keys_and_direct_invalid_updates_are_atomic(mapping_output):
    layer = SourceMappingLayer()
    layer.updateMappings(mapping_output["sourceMappings"])
    previous = layer.sourceMappings
    duplicate = mapping_output["sourceMappings"] + [mapping_output["sourceMappings"][0]]
    for entries in [duplicate, [mapping_output["sourceMappings"][0], {}]]:
        with pytest.raises(ValueError):
            layer.updateMappings(entries)
        assert layer.sourceMappings is previous


@pytest.mark.parametrize(
    "field,value",
    [
        ("fileId", ""),
        ("startLine", 0),
        ("endLine", 1),
        ("startColumn", -1),
        ("endColumn", 0),
        ("startLine", "2"),
        ("endColumn", True),
    ],
)
def test_invalid_source_coordinates(mapping_output, field, value):
    location = {**mapping_output["sourceMappings"][0]["location"], field: value}
    with pytest.raises(ValueError):
        SourceLocation(**location)


def test_mapping_models_keep_opaque_ids_and_allow_zero_width_locations():
    location = SourceLocation("file.py", 1, 1, 0, 0)
    assert SourceMapping("g", "n", location).location is location
    for graph, node, source in [("", "n", location), ("g", None, location), ("g", "n", {})]:
        with pytest.raises(ValueError):
            SourceMapping(graph, node, source)
