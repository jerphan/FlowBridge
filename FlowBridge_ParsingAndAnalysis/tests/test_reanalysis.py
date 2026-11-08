"""Full-snapshot editing lifecycle and concrete final-review regressions."""
import copy
import json
import unittest
from flowbridge_analysis import (ParsingAnalysisService, FlowchartOutput, MappingOutput,
                                 ProjectGraphBuilder, RevisionIds)
from test_pipeline import payload


class ReanalysisTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()
        self.source = 'def choose(x):\n    if x > 0:\n        return x\n    return 0\n'

    def analyze(self, source, revision=1):
        data = payload(('main.py', source))
        data['revisionId'] = revision
        return self.service.analyze_project(data)

    def ids(self, result):
        identifiers = set(result.graphs)
        identifiers.update(f.function_id for f in result.functions)
        identifiers.update(s.scope_id for s in result.symbols)
        identifiers.update(c.call_id for c in result.call_references)
        for graph in result.graphs.values():
            identifiers.update(n.node_id for n in graph.nodes)
            identifiers.update(e.edge_id for e in graph.edges)
        return identifiers

    def check_mappings(self, result, source):
        result.__post_init__()
        lines = source.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        backed = {(g.graph_id, n.node_id) for g in result.graphs.values()
                  for n in g.nodes if n.source_location is not None}
        self.assertEqual(backed, {(m.graph_id, m.node_id) for m in result.source_mappings})
        for mapping in result.source_mappings:
            location = mapping.location
            self.assertLessEqual(location.end_line, len(lines))
            self.assertLessEqual(location.end_column, len(lines[location.end_line-1].encode('utf-8')))
            node = next(n for n in result.graphs[mapping.graph_id].nodes if n.node_id == mapping.node_id)
            self.assertEqual(node.source_location, location)

    def test_initial_and_identical_requests_are_independent(self):
        first = self.analyze(self.source)
        second = self.analyze(self.source)
        self.assertEqual(first.status, 'success')
        self.assertEqual(first.to_json(), second.to_json())
        for graph_id in first.graphs:
            self.assertIsNot(first.graphs[graph_id], second.graphs[graph_id])
        first.graphs.clear()
        self.assertTrue(second.graphs)
        self.check_mappings(second, self.source)

    def test_edit_conditional_refreshes_nodes_and_all_revision_ids(self):
        first = self.analyze(self.source)
        edited = self.source.replace('x > 0', 'x < 10')
        second = self.analyze(edited, 2)
        self.assertFalse(self.ids(first) & self.ids(second))
        labels = [n.label for g in second.graphs.values() for n in g.nodes]
        self.assertIn('x < 10', labels)
        self.assertNotIn('x > 0', labels)
        self.check_mappings(second, edited)
        for output in (second, FlowchartOutput(second), MappingOutput(second)):
            self.assertEqual(output.to_dict()['revisionId'], 2)

    def test_add_function_then_remove_function_and_bindings(self):
        first = self.analyze(self.source)
        added = self.analyze(self.source + '\ndef extra():\n    added = choose(2)\n    return added\n', 2)
        self.assertEqual([f.function_name for f in added.functions], ['choose', 'extra'])
        self.assertTrue(any(s.name == 'added' for s in added.symbols))
        removed = self.analyze('def replacement():\n    return 5\n', 3)
        self.assertEqual([f.function_name for f in removed.functions], ['replacement'])
        self.assertFalse(any(s.name in ('choose', 'extra', 'added') for s in removed.symbols))
        self.assertEqual(removed.call_references, [])
        self.assertEqual(len(removed.graphs), 3)
        self.assertFalse(self.ids(first) & self.ids(removed))

    def test_insert_and_remove_lines_refreshes_unicode_mappings(self):
        source = 'def f():\r\n    café = "é"\r\n    return café\r\n'
        first = self.analyze(source)
        edited = '# new\r\n\r\n' + source
        second = self.analyze(edited, 2)
        self.assertEqual(second.functions[0].start_line, first.functions[0].start_line + 2)
        self.check_mappings(second, edited)
        third = self.analyze(source, 3)
        self.assertEqual(third.functions[0].start_line, 1)
        self.check_mappings(third, source)

    def test_syntax_error_replaces_old_graph_and_recovery_is_fresh(self):
        first = self.analyze(self.source)
        invalid = self.analyze('def choose(:\n', 2)
        self.assertEqual(invalid.status, 'partial')
        self.assertEqual(invalid.functions, [])
        self.assertEqual(invalid.symbols, [])
        self.assertEqual(invalid.source_mappings, [])
        self.assertEqual(invalid.call_references, [])
        self.assertEqual(invalid.files[0].status, 'failed')
        self.assertEqual(invalid.graphs[invalid.files[0].graph_id].nodes, [])
        self.assertTrue(any(d.code == 'SYNTAX_ERROR' for d in invalid.diagnostics))
        self.assertFalse(set(first.graphs) & set(invalid.graphs))
        recovered = self.analyze(self.source, 3)
        self.assertEqual(recovered.status, 'success')
        self.assertFalse(recovered.diagnostics)

    def test_failed_import_target_does_not_reuse_previous_call_target(self):
        data = payload(('calculator.py', 'def add(a,b):\n    return a+b'),
                       ('main.py', 'from calculator import add\ndef main():\n    return add(1,2)'))
        first = self.service.analyze_project(data)
        self.assertEqual(first.call_references[0].resolution, 'resolved')
        data['revisionId'] = 2
        data['files'][0]['fileContent'] = 'def add(:'
        second = self.service.analyze_project(data)
        self.assertEqual(second.call_references[0].resolution, 'unresolved')
        self.assertIsNone(second.call_references[0].target_graph_id)
        self.assertEqual([f.function_name for f in second.functions], ['main'])
        self.assertTrue(all(m.location.file_id == '1' for m in second.source_mappings))

    def test_old_revision_and_reused_revision_are_rebuilt_not_cached(self):
        newest = self.analyze(self.source, 12)
        older = self.analyze('def old():\n    pass', 3)
        self.assertEqual(older.revision_id, 3)
        self.assertEqual(older.functions[0].function_name, 'old')
        edited_same_revision = self.analyze('def other():\n    pass', 12)
        self.assertEqual(edited_same_revision.functions[0].function_name, 'other')
        self.assertEqual(newest.functions[0].function_name, 'choose')

    def test_input_not_mutated_and_other_project_is_isolated(self):
        data = payload(('main.py', self.source))
        original = copy.deepcopy(data)
        first = self.service.analyze_project(data)
        self.assertEqual(data, original)
        data['projectId'] = 'Another'
        second = self.service.analyze_project(data)
        self.assertFalse(self.ids(first) & self.ids(second))

    def test_path_metadata_does_not_crash(self):
        for path in ('.', '/', 'bad\x00.py'):
            with self.subTest(path=path):
                data = payload(('main.py', self.source))
                data['files'][0]['filePath'] = path
                result = self.service.analyze_project(data)
                result.to_json()
                if '\x00' in path:
                    self.assertEqual(result.files[0].status, 'failed')
                    self.assertTrue(any(d.code == 'INVALID_SOURCE_PATH' for d in result.diagnostics))
                else:
                    self.assertEqual(result.status, 'success')

    def test_duplicate_parameter_has_no_executable_cfg(self):
        for signature in ('a,a', 'a,/,a', 'a,*a', 'a,**a'):
            result = self.analyze(f'def f({signature}):\n    return a')
            self.assertEqual(result.status, 'partial')
            graph = result.graphs[result.functions[0].graph_id]
            self.assertEqual(graph.status, 'unsupported')
            self.assertEqual(graph.nodes, [])
            self.assertTrue(any('duplicate parameter' in d.message for d in result.diagnostics))

    def test_builder_dictionary_compatibility_and_noncomplete_project(self):
        result = self.analyze(self.source)
        functions = {f.graph_id: result.graphs[f.graph_id] for f in result.functions}
        built = ProjectGraphBuilder().build(result.files, result.functions, functions,
                                            RevisionIds('P', 1), project_status='failed')
        self.assertEqual(built.project_graph.nodes, [])
        self.assertTrue(all(r.source_graph_id != built.project_graph.graph_id for r in built.graph_references))
        self.assertEqual(set(built.combine_graphs(functions)), set(built.graphs))

    def test_structural_failure_preserves_valid_json_revision(self):
        data = {'projectId': 'P', 'projectName': 'Test', 'revisionId': 27, 'files': None}
        decoded = self.service.analyze_project(data)
        encoded = self.service.analyze_project(json.dumps(data))
        self.assertEqual(decoded.to_dict(), encoded.to_dict())
        self.assertEqual(encoded.status, 'failed')
        for output in (encoded, FlowchartOutput(encoded), MappingOutput(encoded)):
            self.assertEqual(output.to_dict()['revisionId'], 27)
        duplicate = self.service.analyze_project('{"projectId":"P","revisionId":1,"revisionId":2}')
        self.assertIsNone(duplicate.revision_id)

    def test_realistic_order_project(self):
        from pathlib import Path
        data = json.loads(Path('examples/orders_input.json').read_text(encoding='utf-8'))
        result = self.service.analyze_project(data)
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.graphs), 7)
        self.assertEqual(len(result.graph_references), 8)
        resolved = [call for call in result.call_references if call.resolution == 'resolved']
        targets = {f.function_id: f.function_name for f in result.functions}
        self.assertEqual({targets[call.target_function_id] for call in resolved}, {'discounted', 'total_order'})
        self.assertTrue(any(call.resolution == 'builtin' for call in result.call_references))
        for reference in result.graph_references:
            self.assertIn(reference.target_graph_id, result.graphs)
        result.__post_init__()
        self.assertEqual(FlowchartOutput(result).to_dict()['callReferences'],
                         MappingOutput(result).to_dict()['callReferences'])
