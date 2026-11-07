"""Tests for Phase 4 (Loop else Traversal) and Phase 5 (Disconnected End Nodes)."""
import ast
import unittest
from flowbridge_analysis import (ParsingAnalysisService, ASTAnalyzer, CFGBuilder,
                                 FeatureValidator, PythonParser, RevisionIds)
from flowbridge_analysis.models import FileInput


def make_payload(*sources):
    return {
        'projectId': 'P',
        'projectName': 'Phase45Test',
        'revisionId': 1,
        'files': [
            {'fileId': str(i), 'fileName': name, 'filePath': name, 'fileContent': src}
            for i, (name, src) in enumerate(sources)
        ]
    }


class Phase4LoopElseTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def test_for_else_search(self):
        code = (
            "def search(values, target):\n"
            "    for value in values:\n"
            "        if value == target:\n"
            "            return True\n"
            "    else:\n"
            "        return False\n"
        )
        result = self.service.analyze_project(make_payload(('search.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        sym_names = {s.name for s in result.symbols}
        self.assertIn('search', sym_names)
        self.assertIn('values', sym_names)
        self.assertIn('target', sym_names)
        self.assertIn('value', sym_names)

        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = [n.label for n in fn_graph.nodes]
        self.assertIn('Iterate: values', labels)
        self.assertIn('Next: value', labels)
        self.assertIn('value == target', labels)
        self.assertIn('return True', labels)
        self.assertIn('return False', labels)

    def test_while_else_with_break_bypassing_else(self):
        code = (
            "def check(n):\n"
            "    i = 0\n"
            "    found = False\n"
            "    while i < n:\n"
            "        if i == 5:\n"
            "            found = True\n"
            "            break\n"
            "        i += 1\n"
            "    else:\n"
            "        found = False\n"
            "    return found\n"
        )
        result = self.service.analyze_project(make_payload(('check.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = {n.node_id: n.label for n in fn_graph.nodes}
        links = {(labels[e.source_id], labels[e.target_id], e.edge_type) for e in fn_graph.edges}

        # break must bypass else and connect to return found
        self.assertIn(('break', 'return found', 'break'), links)
        # while exhaustion connects to else
        self.assertIn(('i < n', 'found = False', 'false'), links)
        # else finishes and connects to return found
        self.assertIn(('found = False', 'return found', 'next'), links)

    def test_nested_loops_with_else(self):
        code = (
            "def matrix_has_zero(matrix):\n"
            "    for row in matrix:\n"
            "        for val in row:\n"
            "            if val == 0:\n"
            "                break\n"
            "        else:\n"
            "            continue\n"
            "        return True\n"
            "    return False\n"
        )
        result = self.service.analyze_project(make_payload(('matrix.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        sym_names = {s.name for s in result.symbols}
        self.assertIn('row', sym_names)
        self.assertIn('val', sym_names)

    def test_calls_inside_loop_else_are_extracted(self):
        code = (
            "def log_msg(msg):\n"
            "    print(msg)\n"
            "\n"
            "def run(items):\n"
            "    for x in items:\n"
            "        if x > 0:\n"
            "            break\n"
            "    else:\n"
            "        log_msg('no positive found')\n"
        )
        result = self.service.analyze_project(make_payload(('main.py', code)))
        self.assertEqual(result.status, 'success')
        calls = [c for c in result.call_references if 'log_msg' in c.expression]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].resolution, 'resolved')


class Phase5DisconnectedEndNodesTests(unittest.TestCase):
    def setUp(self):
        self.builder = CFGBuilder()

    def _build_fn(self, source: str):
        file = FileInput(file_id='0', file_name='t.py', file_path='t.py', file_content=source)
        tree = ast.parse(source)
        return self.builder.build(tree.body[0], file, RevisionIds('P', 1))

    def test_infinite_loop_without_break_removes_end(self):
        code = "def worker():\n    while True:\n        process()\n"
        res = self._build_fn(code)
        labels = [n.label for n in res.graph.nodes]
        self.assertNotIn('End', labels)
        self.assertIn('Start', labels)
        self.assertIn('process()', labels)

    def test_infinite_loop_with_conditional_break_preserves_end(self):
        code = (
            "def worker(flag):\n"
            "    while True:\n"
            "        if flag:\n"
            "            break\n"
            "        process()\n"
        )
        res = self._build_fn(code)
        labels = [n.label for n in res.graph.nodes]
        self.assertIn('End', labels)

    def test_infinite_loop_with_return_preserves_end(self):
        code = (
            "def worker(flag):\n"
            "    while True:\n"
            "        if flag:\n"
            "            return 1\n"
            "        process()\n"
        )
        res = self._build_fn(code)
        labels = [n.label for n in res.graph.nodes]
        self.assertIn('End', labels)

    def test_conditional_branches_with_mixed_termination(self):
        # Branch 1 returns, Branch 2 infinite loop -> End is reachable via branch 1
        code1 = (
            "def worker(flag):\n"
            "    if flag:\n"
            "        return 1\n"
            "    else:\n"
            "        while True:\n"
            "            process()\n"
        )
        res1 = self._build_fn(code1)
        labels1 = [n.label for n in res1.graph.nodes]
        self.assertIn('End', labels1)

        # Both branches infinite loop -> End is unreachable and removed
        code2 = (
            "def worker(flag):\n"
            "    if flag:\n"
            "        while True:\n"
            "            one()\n"
            "    else:\n"
            "        while True:\n"
            "            two()\n"
        )
        res2 = self._build_fn(code2)
        labels2 = [n.label for n in res2.graph.nodes]
        self.assertNotIn('End', labels2)

    def test_exceptional_termination_in_infinite_loop(self):
        code = (
            "def worker():\n"
            "    try:\n"
            "        while True:\n"
            "            process()\n"
            "    except ZeroDivisionError:\n"
            "        return 0\n"
        )
        res = self._build_fn(code)
        labels = [n.label for n in res.graph.nodes]
        self.assertIn('End', labels)
        self.assertIn('Exceptional End', labels)
