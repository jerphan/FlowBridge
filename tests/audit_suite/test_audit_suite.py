"""Automated Regression & Audit Test Suite for FlowBridge Parsing & Analysis.

Verifies graph models, CFG structures, exception flows, call resolutions,
and diagnostics according to FlowBridge architectural specifications.
"""

import sys
import unittest
from pathlib import Path

# Add Parsing & Analysis src
_root = Path(__file__).resolve().parents[2]
_analysis_src = _root / "FlowBridge_ParsingAndAnalysis" / "src"
if str(_analysis_src) not in sys.path:
    sys.path.insert(0, str(_analysis_src))

from flowbridge_analysis import ParsingAnalysisService
from flowbridge_analysis.models import FileInput, ProjectInput


class TestFlowBridgeParsingAnalysisAudit(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def _analyze(self, files: list[FileInput], project_id: str = "test_p") -> ProjectInput:
        payload = ProjectInput(
            project_id=project_id,
            project_name="Test Project",
            revision_id=1,
            files=files,
        ).to_dict()
        return self.service.analyze_project(payload)

    def test_category_a_basic_control_flow(self):
        code = (
            "def test_func(x):\n"
            "    a = 1\n"
            "    if x > 0:\n"
            "        return a\n"
            "    return -a\n"
        )
        f = FileInput(file_id="f1", file_name="cf.py", file_path="cf.py", file_content=code)
        res = self._analyze([f])
        self.assertEqual(res.status, "success")
        self.assertEqual(len(res.functions), 1)
        fn_graph = res.graphs[res.functions[0].graph_id]
        self.assertEqual(fn_graph.graph_type, "function")
        self.assertEqual(fn_graph.status, "complete")
        types = [n.node_type for n in fn_graph.nodes]
        self.assertIn("start", types)
        self.assertIn("condition", types)
        self.assertIn("return", types)
        self.assertIn("end", types)

    def test_category_b_exception_handling_basic(self):
        code = (
            "def test_try(x):\n"
            "    try:\n"
            "        y = 10 // x\n"
            "        return y\n"
            "    except ZeroDivisionError:\n"
            "        return 0\n"
        )
        f = FileInput(file_id="f1", file_name="exc.py", file_path="exc.py", file_content=code)
        res = self._analyze([f])
        self.assertEqual(res.status, "success")
        fn_graph = res.graphs[res.functions[0].graph_id]
        types = [n.node_type for n in fn_graph.nodes]
        self.assertIn("exceptionDispatch", types)
        self.assertIn("handler", types)
        edge_types = [e.edge_type for e in fn_graph.edges]
        self.assertIn("exception", edge_types)

    def test_category_c_module_level_execution(self):
        code = "x = 10\ny = 20\nprint(x + y)\n"
        f = FileInput(file_id="f1", file_name="mod.py", file_path="mod.py", file_content=code)
        res = self._analyze([f])
        self.assertEqual(res.status, "success")
        file_graph = next(g for g in res.graphs.values() if g.graph_type == "file")
        self.assertEqual(file_graph.status, "complete")
        labels = [n.label for n in file_graph.nodes]
        self.assertIn("x = 10", labels)
        self.assertIn("y = 20", labels)
        self.assertIn("print(x + y)", labels)

    def test_category_d_same_file_calls_resolution(self):
        code = (
            "def add(a, b):\n"
            "    return a + b\n\n"
            "def main():\n"
            "    res = add(1, 2)\n"
            "    return res\n\n"
            "main()\n"
        )
        f = FileInput(file_id="f1", file_name="same.py", file_path="same.py", file_content=code)
        res = self._analyze([f])
        self.assertEqual(res.status, "success")
        resolved_calls = [c for c in res.call_references if c.resolution == "resolved"]
        self.assertTrue(any(c.expression == "add(1, 2)" for c in resolved_calls))

        # Phase 3 Verification: In Function View of main(), the call is a clickable function node
        main_fn = next(f for f in res.functions if f.function_name == "main")
        add_fn = next(f for f in res.functions if f.function_name == "add")
        main_graph = res.graphs[main_fn.graph_id]
        call_node = next(n for n in main_graph.nodes if "add(1, 2)" in n.label)
        self.assertEqual(call_node.node_type, "function")
        call_ref = next(r for r in res.graph_references
                        if r.source_graph_id == main_graph.graph_id and r.source_node_id == call_node.node_id)
        self.assertEqual(call_ref.target_graph_id, add_fn.graph_id)
        self.assertEqual(call_node.source_location.start_line, 5)

    def test_category_e_cross_file_call_resolution(self):
        f_calc = FileInput(file_id="f_calc", file_name="calculator.py", file_path="calculator.py",
                           file_content="def add(a, b):\n    return a + b\n")
        f_main = FileInput(file_id="f_main", file_name="main.py", file_path="main.py",
                           file_content="from calculator import add\nres = add(1, 2)\n")
        res = self._analyze([f_calc, f_main])
        self.assertEqual(res.status, "success")
        calc_call = next((c for c in res.call_references if c.expression == "add(1, 2)"), None)
        self.assertIsNotNone(calc_call)
        self.assertEqual(calc_call.resolution, "resolved")
        self.assertIsNotNone(calc_call.target_function_id)

        # Phase 3 Verification: In File View of main.py, the cross-file call has a function node and GraphReference
        main_file = next(f for f in res.files if f.file_name == "main.py")
        main_file_graph = res.graphs[main_file.graph_id]
        call_node = next(n for n in main_file_graph.nodes if "add(1, 2)" in n.label)
        self.assertEqual(call_node.node_type, "function")
        ref = next(r for r in res.graph_references
                   if r.source_graph_id == main_file_graph.graph_id and r.source_node_id == call_node.node_id)
        self.assertEqual(ref.target_graph_id, calc_call.target_graph_id)
        self.assertEqual(call_node.source_location.start_line, 2)

    def test_category_g_recursion_bounding(self):
        code = (
            "def rec(n):\n"
            "    if n <= 0: return 0\n"
            "    return n + rec(n - 1)\n\n"
            "rec(5)\n"
        )
        f = FileInput(file_id="f1", file_name="rec.py", file_path="rec.py", file_content=code)
        res = self._analyze([f])
        self.assertEqual(res.status, "success")
        file_graph = next(g for g in res.graphs.values() if g.graph_type == "file")
        rec_nodes = [n for n in file_graph.nodes if "(recursive)" in n.label]
        self.assertTrue(len(rec_nodes) > 0)

    def test_category_h_unsupported_classes_partial_failure(self):
        f_good = FileInput(file_id="f_good", file_name="good.py", file_path="good.py",
                           file_content="def add(a, b): return a + b\n")
        f_bad = FileInput(file_id="f_bad", file_name="bad.py", file_path="bad.py",
                          file_content="class MyClass:\n    pass\n")
        res = self._analyze([f_good, f_bad])
        self.assertEqual(res.status, "partial")
        f_good_meta = next(f for f in res.files if f.file_id == "f_good")
        f_bad_meta = next(f for f in res.files if f.file_id == "f_bad")
        self.assertEqual(f_good_meta.status, "complete")
        self.assertEqual(f_bad_meta.status, "unsupported")
        self.assertTrue(any(d.code == "UNSUPPORTED_FEATURE" for d in res.diagnostics))

    def test_category_i_syntax_error_reporting(self):
        f_good = FileInput(file_id="f_good", file_name="good.py", file_path="good.py",
                           file_content="def add(a, b): return a + b\n")
        f_bad = FileInput(file_id="f_bad", file_name="bad.py", file_path="bad.py",
                          file_content="def broken(x):\n    try:\n        return x\n    except ValueError\n        return None\n")
        res = self._analyze([f_good, f_bad])
        self.assertEqual(res.status, "partial")
        f_bad_meta = next(f for f in res.files if f.file_id == "f_bad")
        self.assertEqual(f_bad_meta.status, "failed")
        syntax_diag = next((d for d in res.diagnostics if d.code == "SYNTAX_ERROR"), None)
        self.assertIsNotNone(syntax_diag)
        self.assertEqual(syntax_diag.file_id, "f_bad")
        self.assertIsNotNone(syntax_diag.source_location)
        self.assertEqual(syntax_diag.source_location.start_line, 4)


if __name__ == "__main__":
    unittest.main()
