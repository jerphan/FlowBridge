"""File views must preserve call resolution, terminal flow, and failure isolation."""

import unittest
from unittest.mock import patch

from test_pipeline import payload

from flowbridge_analysis import CFGBuilder, ParsingAnalysisService


class FileFlowRegressions(unittest.TestCase):
    def test_parameter_shadowing_does_not_inline_a_global_function(self):
        source = (
            "def helper():\n    return 1\ndef run(helper):\n"
            "    return helper()\nanswer = run(print)\n"
        )
        result = ParsingAnalysisService().analyze_project(payload(("main.py", source)))
        call = next(c for c in result.call_references if c.expression == "helper()")
        self.assertEqual(call.resolution, "unresolved")
        labels = [node.label for node in result.graphs[result.files[0].graph_id].nodes]
        self.assertIn("return helper()", labels)
        self.assertNotIn("return 1", labels)

    def test_returning_an_inlined_call_does_not_reach_following_statements(self):
        source = (
            "def inner():\n    return 1\ndef outer():\n"
            '    return inner()\n    print("unreachable")\nanswer = outer()\n'
            'print("after call")\n'
        )
        result = ParsingAnalysisService().analyze_project(payload(("main.py", source)))
        graph = result.graphs[result.files[0].graph_id]
        labels = [node.label for node in graph.nodes]
        self.assertIn("return inner()", labels)
        self.assertNotIn('print("unreachable")', labels)
        self.assertIn('print("after call")', labels)

    def test_file_view_failure_remains_partial_with_valid_function_views(self):
        original = CFGBuilder.build_file

        def fail_one_file(builder, tree, file_input, ids, **kwargs):
            if file_input.file_name == "broken.py":
                raise RuntimeError("simulated file view failure")
            return original(builder, tree, file_input, ids, **kwargs)

        with patch.object(CFGBuilder, "build_file", fail_one_file):
            result = ParsingAnalysisService().analyze_project(
                payload(
                    ("broken.py", "def still_valid():\n    return 1\n"),
                    ("good.py", "x = 2\n"),
                )
            )
        self.assertEqual(result.status, "partial")
        failed = next(file for file in result.files if file.file_name == "broken.py")
        self.assertEqual(failed.status, "unsupported")
        self.assertEqual(result.graphs[failed.graph_id].status, "failed")
        self.assertEqual(result.graphs[failed.graph_id].nodes, [])
        self.assertEqual(result.graphs[result.functions[0].graph_id].status, "complete")
        good = next(file for file in result.files if file.file_name == "good.py")
        self.assertEqual(result.graphs[good.graph_id].status, "complete")
        result.to_json()
