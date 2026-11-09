"""Check cleanup paths without executing the submitted Python."""

import unittest

from flowbridge_analysis import ParsingAnalysisService


def analyze(source):
    return ParsingAnalysisService().analyze_project({
        'projectId': 'cleanup', 'projectName': 'Cleanup', 'revisionId': 2,
        'files': [{'fileId': 'main', 'fileName': 'main.py', 'filePath': 'main.py',
                   'fileContent': source}],
    })


def reachable(graph, source, target, excluded=()):
    pending = [source]
    visited = set(excluded)
    while pending:
        node = pending.pop()
        if node in visited:
            continue
        if node == target:
            return True
        visited.add(node)
        pending.extend(edge.target_id for edge in graph.edges if edge.source_id == node)
    return False


class FinallyRegressions(unittest.TestCase):
    def graphs(self, source):
        result = analyze(source + '\nresult = run()\n')
        self.assertEqual(result.status, 'success', [d.message for d in result.diagnostics])
        result.to_json()
        return [graph for graph in result.graphs.values() if graph.graph_type in ('function', 'file')]

    def must_visit(self, graph, trigger, cleanup, destination):
        starts = [n.node_id for n in graph.nodes if n.label == trigger]
        cleanups = [n.node_id for n in graph.nodes if n.label == cleanup]
        targets = [n.node_id for n in graph.nodes if n.label == destination]
        self.assertTrue(starts, trigger)
        self.assertTrue(cleanups, cleanup)
        self.assertTrue(targets, destination)
        for start in starts:
            self.assertTrue(any(reachable(graph, start, target) for target in targets))
            self.assertFalse(any(reachable(graph, start, target, cleanups) for target in targets))

    def test_return_runs_finally_in_function_and_inlined_file(self):
        for graph in self.graphs('def run():\n    try:\n        return 1\n    finally:\n        cleanup = 2\n'):
            with self.subTest(view=graph.graph_type):
                self.must_visit(graph, 'return 1', 'cleanup = 2', 'End')

    def test_raise_runs_finally_before_exceptional_end(self):
        for graph in self.graphs("def run():\n    try:\n        raise ValueError('bad')\n    finally:\n        cleanup = 2\n"):
            with self.subTest(view=graph.graph_type):
                self.must_visit(graph, "raise ValueError('bad')", 'cleanup = 2', 'Exceptional End')

    def test_break_runs_finally_before_leaving_loop(self):
        for graph in self.graphs('def run():\n    while True:\n        try:\n            break\n        finally:\n            cleanup = 2\n    finished = 3\n'):
            with self.subTest(view=graph.graph_type):
                self.must_visit(graph, 'break', 'cleanup = 2', 'finished = 3')

    def test_continue_runs_finally_before_loop_header(self):
        for graph in self.graphs('def run():\n    while True:\n        try:\n            continue\n        finally:\n            cleanup = 2\n'):
            with self.subTest(view=graph.graph_type):
                self.must_visit(graph, 'continue', 'cleanup = 2', 'True')

    def test_finally_return_replaces_pending_return(self):
        for graph in self.graphs('def run():\n    try:\n        return 1\n    finally:\n        return 2\n'):
            with self.subTest(view=graph.graph_type):
                self.must_visit(graph, 'return 1', 'return 2', 'End')

    def test_finally_raise_replaces_pending_return(self):
        for graph in self.graphs("def run():\n    try:\n        return 1\n    finally:\n        raise RuntimeError('cleanup')\n"):
            with self.subTest(view=graph.graph_type):
                self.must_visit(graph, 'return 1', "raise RuntimeError('cleanup')", 'Exceptional End')
                self.assertFalse(any(n.label == 'End' for n in graph.nodes))

    def test_nested_finally_keeps_both_cleanups(self):
        source = ('def run():\n    try:\n        try:\n            return 1\n'
                  '        finally:\n            inner_cleanup = 2\n'
                  '    finally:\n        outer_cleanup = 3\n')
        for graph in self.graphs(source):
            with self.subTest(view=graph.graph_type):
                self.must_visit(graph, 'return 1', 'inner_cleanup = 2', 'End')
                self.must_visit(graph, 'return 1', 'outer_cleanup = 3', 'End')

    def test_normal_and_return_paths_do_not_share_continuations(self):
        source = ('def run():\n    try:\n        if flag:\n            return 1\n'
                  '        value = 2\n    finally:\n        cleanup = 3\n    after = 4\n')
        result = analyze(source)
        graph = next(g for g in result.graphs.values() if g.graph_type == 'function')
        returned = next(n for n in graph.nodes if n.label == 'return 1')
        after = next(n for n in graph.nodes if n.label == 'after = 4')
        self.assertFalse(reachable(graph, returned.node_id, after.node_id))
        self.must_visit(graph, 'value = 2', 'cleanup = 3', 'after = 4')

    def test_unhandled_inner_exception_reaches_outer_handler(self):
        source = ('def run():\n    try:\n        try:\n            raise ValueError()\n'
                  '        except TypeError:\n            pass\n'
                  '    except ValueError:\n        recovered = 1\n')
        result = analyze(source)
        graph = next(g for g in result.graphs.values() if g.graph_type == 'function')
        self.assertTrue(any(n.label == 'recovered = 1' for n in graph.nodes))
        dispatches = {n.node_id for n in graph.nodes if n.node_type == 'exceptionDispatch'}
        self.assertTrue(any(e.edge_type == 'unhandled' and e.target_id in dispatches for e in graph.edges))
