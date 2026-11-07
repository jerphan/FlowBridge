"""End-to-end hierarchy, failure isolation and shared projection identities."""
import json
from pathlib import Path
import unittest
from flowbridge_analysis import (ParsingAnalysisService, FlowchartOutput, MappingOutput,
                                 ProjectGraphBuilder, RevisionIds)


def payload(*sources):
    return {'projectId': 'P', 'projectName': 'Test', 'revisionId': 1,
            'files': [{'fileId': str(i), 'fileName': name, 'filePath': name, 'fileContent': source}
                      for i, (name, source) in enumerate(sources)]}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def check_integrity(self, result):
        result.__post_init__()
        expected = {(g.graph_id, n.node_id) for g in result.graphs.values()
                    for n in g.nodes if n.source_location is not None}
        self.assertEqual(expected, {(m.graph_id, m.node_id) for m in result.source_mappings})
        for reference in result.graph_references:
            self.assertIn(reference.target_graph_id, result.graphs)
            self.assertIn(reference.source_node_id,
                          [n.node_id for n in result.graphs[reference.source_graph_id].nodes])
        for graph in result.graphs.values():
            if graph.graph_type not in ('function', 'module'):
                self.assertEqual(graph.edges, [])

    def test_calculator_projections(self):
        source = Path('examples/calculator_input.json').read_text(encoding='utf-8')
        result = self.service.analyze_project(source)
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.functions), 2)
        self.assertEqual(len(result.graphs), 4)
        self.check_integrity(result)
        kevin = FlowchartOutput(result).to_dict()
        grace = MappingOutput(result).to_dict()
        self.assertEqual(kevin['graphReferences'], grace['graphReferences'])
        self.assertEqual(kevin['revisionId'], grace['revisionId'])
        self.assertEqual(len(grace['callReferences']), 2)
        self.assertEqual(json.loads(FlowchartOutput(result).to_json()), kevin)
        for mapping in grace['sourceMappings']:
            self.assertIn(mapping['nodeId'], [n['nodeId'] for n in kevin['graphs'][mapping['graphId']]['nodes']])

    def test_multifile_import_call(self):
        result = self.service.analyze_project(payload(
            ('calculator.py', 'def add(a,b):\n    return a+b'),
            ('main.py', 'from calculator import add\ndef main():\n    return add(10,5)')))
        self.assertEqual(result.status, 'success')  # Absolute imports are supported metadata.
        self.assertEqual(result.call_references[0].resolution, 'resolved')
        self.assertIn(result.call_references[0].target_graph_id, result.graphs)
        self.assertEqual(len(result.graph_references), 4)
        self.check_integrity(result)

    def test_empty_file_and_project(self):
        result = self.service.analyze_project(payload(('empty.py', '')))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.graphs), 2)
        self.assertEqual(len(result.graph_references), 1)
        self.check_integrity(result)
        empty = self.service.analyze_project(payload())
        self.assertEqual(len(empty.graphs), 1)
        self.assertEqual(empty.status, 'success')

    def test_invalid_file_keeps_sibling(self):
        result = self.service.analyze_project(payload(('bad.py', 'def !'), ('good.py', 'def f():\n    pass')))
        self.assertEqual(result.status, 'partial')
        self.assertEqual(result.files[0].status, 'failed')
        self.assertEqual(result.graphs[result.files[0].graph_id].nodes, [])
        self.assertEqual(len(result.functions), 1)
        self.check_integrity(result)

    def test_module_execution_and_unsupported_function(self):
        result = self.service.analyze_project(payload(('m.py', 'run()\ndef f():\n    with x:\n        pass')))
        self.assertEqual(result.status, 'partial')
        function = result.functions[0]
        self.assertEqual(result.graphs[function.graph_id].status, 'unsupported')
        self.assertEqual(result.graphs[function.graph_id].nodes, [])
        self.assertEqual(len(result.graphs[result.files[0].graph_id].nodes), 2)
        self.check_integrity(result)

    def test_invalid_input_has_no_graphs(self):
        for value in ['{', {}, {'revisionId': True}]:
            result = self.service.analyze_project(value)
            self.assertEqual(result.status, 'failed')
            self.assertEqual(result.graphs, {})
            self.assertTrue(result.diagnostics)
            MappingOutput(result).to_json()

    def test_reuse_determinism_and_revision_isolation(self):
        data = payload(('m.py', 'def f():\n    f()'))
        first = self.service.analyze_project(data)
        self.assertEqual(first.to_dict(), self.service.analyze_project(data).to_dict())
        data['revisionId'] = 2
        second = self.service.analyze_project(data)
        self.assertFalse(set(first.graphs) & set(second.graphs))
        self.assertEqual(len(self.service.analyze_project(payload()).functions), 0)

    def test_projection_is_independent(self):
        result = self.service.analyze_project(payload(('m.py', '')))
        output = FlowchartOutput(result)
        snapshot = output.to_dict()
        result.graphs.clear()
        self.assertEqual(output.to_dict(), snapshot)
        snapshot['graphs'].clear()
        self.assertTrue(output.to_dict()['graphs'])

    def test_builder_rejects_duplicate_and_missing_graphs(self):
        result = self.service.analyze_project(payload(('m.py', 'def f():\n    pass')))
        graph = result.graphs[result.functions[0].graph_id]
        builder = ProjectGraphBuilder()
        for graphs in [[], [graph, graph]]:
            with self.assertRaises(ValueError):
                builder.build(result.files, result.functions, graphs, RevisionIds('P', 1))
        hierarchy = builder.build(result.files, result.functions, [graph], RevisionIds('P', 1))
        self.assertIs(hierarchy.graphs[graph.graph_id], graph)

    def test_approved_flowchart_metadata_and_import_bindings(self):
        result = self.service.analyze_project(payload(('m.py', 'import math\ndef f():\n    return math.sqrt(4)')))
        kevin = FlowchartOutput(result).to_dict()
        grace = MappingOutput(result).to_dict()
        self.assertEqual(kevin['files'], grace['files'])
        self.assertEqual(kevin['functions'], grace['functions'])
        self.assertEqual(kevin['callReferences'], grace['callReferences'])
        self.assertTrue(any(s['kind'] == 'import' and s['importTarget'] == 'math' for s in kevin['symbols']))

    def test_unicode_crlf_mapping_positions(self):
        source = 'def f():\r\n    café = "é"\r\n    return café\r\n'
        result = self.service.analyze_project(payload(('m.py', source)))
        self.check_integrity(result)
        lines = source.splitlines()
        for mapping in result.source_mappings:
            location = mapping.location
            self.assertLessEqual(location.end_column, len(lines[location.end_line - 1].encode('utf-8')))
        self.assertEqual(result.status, 'success')
