"""Tests for Phase 2 (Augmented and Annotated Assignments) and
Phase 3 (try/except AST Traversal and Bounded Exception CFG).
"""
import ast
import unittest
from flowbridge_analysis import (ParsingAnalysisService, ASTAnalyzer, CFGBuilder,
                                 FeatureValidator, PythonParser, RevisionIds)
from flowbridge_analysis.models import FileInput


def make_payload(*sources):
    return {
        'projectId': 'P',
        'projectName': 'Phase23Test',
        'revisionId': 1,
        'files': [
            {'fileId': str(i), 'fileName': name, 'filePath': name, 'fileContent': src}
            for i, (name, src) in enumerate(sources)
        ]
    }


class Phase2AugmentedAnnotatedAssignmentsTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def test_chained_augmented_assignments(self):
        code = (
            "def calculate():\n"
            "    x = 10\n"
            "    x += 5\n"
            "    x -= 2\n"
            "    x *= 3\n"
            "    x /= 2\n"
            "    return x\n"
        )
        result = self.service.analyze_project(make_payload(('calc.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        # Check symbol binding
        symbols = [s for s in result.symbols if s.name == 'x']
        self.assertTrue(len(symbols) >= 1)

        # Check CFG nodes
        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = [n.label for n in fn_graph.nodes]
        self.assertIn('x = 10', labels)
        self.assertIn('x += 5', labels)
        self.assertIn('x -= 2', labels)
        self.assertIn('x *= 3', labels)
        self.assertIn('x /= 2', labels)
        self.assertIn('return x', labels)

        # Check source mappings exist for every statement node
        stmt_nodes = [n for n in fn_graph.nodes if n.node_type == 'statement']
        self.assertEqual(len(stmt_nodes), 5)
        for sn in stmt_nodes:
            self.assertIsNotNone(sn.source_location)
            self.assertTrue(any(m.node_id == sn.node_id for m in result.source_mappings))

    def test_annotated_assignment_with_augmented_update(self):
        code = (
            "def calculate():\n"
            "    total: int = 10\n"
            "    total += 5\n"
            "    return total\n"
        )
        result = self.service.analyze_project(make_payload(('total.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = [n.label for n in fn_graph.nodes]
        self.assertIn('total: int = 10', labels)
        self.assertIn('total += 5', labels)

    def test_loop_increment(self):
        code = (
            "def loop_inc():\n"
            "    x = 0\n"
            "    for i in range(10):\n"
            "        x += 1\n"
            "    return x\n"
        )
        result = self.service.analyze_project(make_payload(('loop.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = [n.label for n in fn_graph.nodes]
        self.assertIn('x += 1', labels)

    def test_augmented_assignment_with_subscript(self):
        code = (
            "def list_inc():\n"
            "    items = [1, 2, 3]\n"
            "    items[0] += 10\n"
            "    return items\n"
        )
        result = self.service.analyze_project(make_payload(('subscript.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = [n.label for n in fn_graph.nodes]
        self.assertIn('items[0] += 10', labels)

    def test_annotated_assignment_without_value(self):
        code = (
            "def annot_only():\n"
            "    x: int\n"
            "    x = 5\n"
            "    return x\n"
        )
        result = self.service.analyze_project(make_payload(('annot.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        symbols = [s for s in result.symbols if s.name == 'x']
        self.assertTrue(len(symbols) >= 1)

        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = [n.label for n in fn_graph.nodes]
        self.assertIn('x: int', labels)

    def test_unsupported_annotation_expressions_receive_diagnostics(self):
        # Lambda in annotation
        res1 = self.service.analyze_project(make_payload(('bad1.py', 'def f():\n    x: (lambda: 1) = 1\n    return x\n')))
        self.assertEqual(res1.status, 'partial')
        self.assertTrue(any(d.code == 'UNSUPPORTED_FEATURE' for d in res1.diagnostics))

        # List comprehension in annotation
        res2 = self.service.analyze_project(make_payload(('bad2.py', 'def f():\n    x: [i for i in range(5)] = 1\n    return x\n')))
        self.assertEqual(res2.status, 'partial')
        self.assertTrue(any(d.code == 'UNSUPPORTED_FEATURE' for d in res2.diagnostics))


class Phase3TryExceptTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def test_safe_divide_complete_traversal_and_symbols(self):
        code = (
            "def safe_divide(a, b):\n"
            "    try:\n"
            "        result = a / b\n"
            "        return result\n"
            "    except ZeroDivisionError:\n"
            "        return 0\n"
        )
        result = self.service.analyze_project(make_payload(('safe.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertFalse(any(d.code == 'INCOMPLETE_SCOPE' for d in result.diagnostics))

        # Check symbol bindings inside try body are recorded
        sym_names = {s.name for s in result.symbols}
        self.assertIn('result', sym_names)
        self.assertIn('a', sym_names)
        self.assertIn('b', sym_names)

        fn_graph = result.graphs[result.functions[0].graph_id]
        self.assertEqual(fn_graph.status, 'complete')

    def test_calls_inside_try_and_except_are_extracted_and_resolved(self):
        code = (
            "def notify(msg):\n"
            "    print(msg)\n"
            "\n"
            "def run():\n"
            "    try:\n"
            "        notify('start')\n"
            "    except:\n"
            "        notify('failed')\n"
        )
        result = self.service.analyze_project(make_payload(('main.py', code)))
        self.assertEqual(result.status, 'success')

        notify_calls = [c for c in result.call_references if 'notify' in c.expression]
        self.assertEqual(len(notify_calls), 2)
        for c in notify_calls:
            self.assertEqual(c.resolution, 'resolved')
            self.assertEqual(c.target_function_id, result.functions[0].function_id)

    def test_unrelated_statements_outside_try_have_no_false_exception_edges(self):
        code = (
            "def process():\n"
            "    before = 1\n"
            "    try:\n"
            "        mid = 2\n"
            "    except:\n"
            "        rec = 3\n"
            "    after = 4\n"
            "    return after\n"
        )
        result = self.service.analyze_project(make_payload(('proc.py', code)))
        self.assertEqual(result.status, 'success')

        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = {n.node_id: n.label for n in fn_graph.nodes}
        links = {(labels[e.source_id], labels[e.target_id], e.edge_type) for e in fn_graph.edges}

        # Verify before = 1 has NO exception edge
        self.assertNotIn(('before = 1', 'Exceptional End', 'exception'), links)
        self.assertNotIn(('before = 1', 'Exception dispatch', 'exception'), links)

        # Verify after = 4 has NO exception edge
        self.assertNotIn(('after = 4', 'Exceptional End', 'exception'), links)
        self.assertNotIn(('after = 4', 'Exception dispatch', 'exception'), links)

        # Verify return after has NO Evaluate return node with exception edge
        self.assertFalse(any(src == 'Evaluate return: after' for src, _, _ in links))

        # Verify mid = 2 DOES have exception edge to Exception dispatch
        self.assertIn(('mid = 2', 'Exception dispatch', 'exception'), links)

        # Verify rec = 3 DOES have exception edge to Exceptional End
        self.assertIn(('rec = 3', 'Exceptional End', 'exception'), links)

    def test_unsupported_exception_constructs_rejected(self):
        cases = [
            "def f():\n    try:\n        x = 1\n    finally:\n        x = 2\n",
            "def f():\n    try:\n        x = 1\n    except:\n        x = 2\n    else:\n        x = 3\n",
            "def f():\n    try:\n        x = 1\n    except Exception as e:\n        pass\n",
            "def f():\n    try:\n        try:\n            x = 1\n        except:\n            pass\n    except:\n        pass\n",
        ]
        for src in cases:
            with self.subTest(src=src):
                result = self.service.analyze_project(make_payload(('test.py', src)))
                self.assertEqual(result.status, 'partial')
                self.assertTrue(any(d.code == 'UNSUPPORTED_FEATURE' for d in result.diagnostics))
