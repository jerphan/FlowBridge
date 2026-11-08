"""Supported static imports must not be rejected as runtime module statements."""
import ast
import unittest
from flowbridge_analysis import FeatureValidator, ParsingAnalysisService
from test_pipeline import payload


class ImportFeatureTests(unittest.TestCase):
    def test_absolute_imports_and_aliases_are_supported_metadata(self):
        source = 'import calculator as c\nfrom calculator import add as plus, subtract\ndef f():\n    return plus(1,2)'
        result = FeatureValidator().validate(ast.parse(source), 'F')
        self.assertTrue(result.is_supported)
        self.assertEqual(result.diagnostics, [])

    def test_unsupported_import_forms_still_report_errors(self):
        for source in ('from .calculator import add', 'from calculator import *',
                       'from __future__ import annotations',
                       'def f():\n    import calculator',
                       'if flag:\n    from calculator import add'):
            with self.subTest(source=source):
                result = FeatureValidator().validate(ast.parse(source), 'F')
                self.assertFalse(result.is_supported)
                self.assertTrue(any(d.code == 'UNSUPPORTED_FEATURE' for d in result.diagnostics))

    def test_cross_file_resolution_and_graphs_without_import_errors(self):
        result = ParsingAnalysisService().analyze_project(payload(
            ('calculator.py', 'def add(a,b):\n    return a+b'),
            ('main.py', 'from calculator import add as plus\ndef main():\n    return plus(1,2)')))
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.diagnostics, [])
        self.assertEqual(result.call_references[0].resolution, 'resolved')
        self.assertIn(result.call_references[0].target_graph_id, result.graphs)
        project_graph = next(g for g in result.graphs.values() if g.graph_type == 'project')
        self.assertTrue(len(project_graph.edges) >= 1)

    def test_external_import_does_not_imply_resolved_target(self):
        result = ParsingAnalysisService().analyze_project(payload(
            ('main.py', 'import nonexistent_library as lib\ndef main():\n    return lib.work()')))
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.call_references[0].resolution, 'external')
        self.assertIsNone(result.call_references[0].target_graph_id)
