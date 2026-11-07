"""Comprehensive test suite for Phase 7 (Robust Error Handling) and
Phase 8 (Required Test Scenarios & Regression Verification).
"""
import ast
import json
import unittest
from flowbridge_analysis import (
    ParsingAnalysisService,
    FlowchartOutput,
    MappingOutput,
    CFGBuilder,
    PythonParser,
    FeatureValidator,
    RevisionIds,
)
from flowbridge_analysis.models import FileInput


def make_payload(*sources):
    return {
        "projectId": "P",
        "projectName": "Phase78Test",
        "revisionId": 1,
        "files": [
            {"fileId": str(i), "fileName": name, "filePath": name, "fileContent": src}
            for i, (name, src) in enumerate(sources)
        ],
    }


class Phase7And8ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def _graph_links(self, graph):
        labels = {n.node_id: n.label for n in graph.nodes}
        return {(labels[e.source_id], labels[e.target_id], e.edge_type) for e in graph.edges}

    # 1. Top-level sequential script
    def test_scenario_01_toplevel_sequential_script(self):
        code = "a = 1\nb = 2\nc = a + b\n"
        result = self.service.analyze_project(make_payload(("seq.py", code)))
        self.assertEqual(result.status, "success")
        mod_graph = [g for g in result.graphs.values() if g.graph_type == "module"][0]
        links = self._graph_links(mod_graph)
        self.assertIn(("Start", "a = 1", "next"), links)
        self.assertIn(("a = 1", "b = 2", "next"), links)
        self.assertIn(("b = 2", "c = a + b", "next"), links)
        self.assertIn(("c = a + b", "End", "next"), links)

    # 2. Top-level if/else
    def test_scenario_02_toplevel_if_else(self):
        code = "x = 10\nif x > 5:\n    y = 1\nelse:\n    y = 2\nz = y\n"
        result = self.service.analyze_project(make_payload(("branch.py", code)))
        self.assertEqual(result.status, "success")
        mod_graph = [g for g in result.graphs.values() if g.graph_type == "module"][0]
        links = self._graph_links(mod_graph)
        self.assertIn(("x > 5", "y = 1", "true"), links)
        self.assertIn(("x > 5", "y = 2", "false"), links)
        self.assertIn(("y = 1", "z = y", "next"), links)
        self.assertIn(("y = 2", "z = y", "next"), links)

    # 3. Top-level for and while
    def test_scenario_03_toplevel_for_and_while(self):
        code = (
            "total = 0\n"
            "for i in [1, 2, 3]:\n"
            "    total += i\n"
            "while total > 0:\n"
            "    total -= 1\n"
        )
        result = self.service.analyze_project(make_payload(("loops.py", code)))
        self.assertEqual(result.status, "success")
        mod_graph = [g for g in result.graphs.values() if g.graph_type == "module"][0]
        labels = [n.label for n in mod_graph.nodes]
        self.assertIn("Iterate: [1, 2, 3]", labels)
        self.assertIn("Next: i", labels)
        self.assertIn("total += i", labels)
        self.assertIn("total > 0", labels)
        self.assertIn("total -= 1", labels)

    # 4. Module-level function calls
    def test_scenario_04_module_level_function_calls(self):
        code = "def compute(x):\n    return x * 2\n\nval = compute(5)\nprint(val)\n"
        result = self.service.analyze_project(make_payload(("main.py", code)))
        self.assertEqual(result.status, "success")
        compute_call = [c for c in result.call_references if "compute" in c.expression][0]
        self.assertEqual(compute_call.resolution, "resolved")
        self.assertEqual(compute_call.target_function_id, result.functions[0].function_id)

    # 5. Multiple functions in one file
    def test_scenario_05_multiple_functions_in_one_file(self):
        code = (
            "def add(a, b):\n    return a + b\n\n"
            "def multiply(a, b):\n    return a * b\n\n"
            "def helper():\n    return 42\n"
        )
        result = self.service.analyze_project(make_payload(("math_utils.py", code)))
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.functions), 3)
        fn_names = {f.function_name for f in result.functions}
        self.assertEqual(fn_names, {"add", "multiply", "helper"})
        file_graph = result.graphs[result.files[0].graph_id]
        file_node_labels = {n.label for n in file_graph.nodes}
        self.assertTrue({"add", "multiply", "helper"}.issubset(file_node_labels))

    # 6. Augmented assignment inside loops
    def test_scenario_06_augmented_assignment_inside_loops(self):
        code = (
            "def accumulate(nums):\n"
            "    total = 0\n"
            "    for n in nums:\n"
            "        total += n\n"
            "    return total\n"
        )
        result = self.service.analyze_project(make_payload(("acc.py", code)))
        self.assertEqual(result.status, "success")
        fn_graph = result.graphs[result.functions[0].graph_id]
        aug_node = [n for n in fn_graph.nodes if n.label == "total += n"][0]
        self.assertIsNotNone(aug_node.source_location)
        self.assertTrue(any(m.node_id == aug_node.node_id for m in result.source_mappings))

    # 7. Basic annotated assignments
    def test_scenario_07_basic_annotated_assignments(self):
        code = (
            "def types_demo():\n"
            "    count: int = 0\n"
            "    ratio: float = 3.14\n"
            "    flag: bool\n"
            "    flag = True\n"
            "    return count\n"
        )
        result = self.service.analyze_project(make_payload(("demo.py", code)))
        self.assertEqual(result.status, "success")
        sym_names = {s.name for s in result.symbols}
        self.assertTrue({"count", "ratio", "flag"}.issubset(sym_names))

    # 8. Supported try/except
    def test_scenario_08_supported_try_except(self):
        code = (
            "def safe_get(xs, index):\n"
            "    try:\n"
            "        return xs[index]\n"
            "    except IndexError:\n"
            "        return None\n"
        )
        result = self.service.analyze_project(make_payload(("safe.py", code)))
        self.assertEqual(result.status, "success")
        self.assertFalse(any(d.severity == "error" for d in result.diagnostics))
        self.assertTrue(any(d.code == "CONSERVATIVE_EXCEPTIONS" for d in result.diagnostics))

    # 9. try/except with local symbols and function calls
    def test_scenario_09_try_except_with_symbols_and_calls(self):
        code = (
            "def log(msg):\n    print(msg)\n\n"
            "def parse_data(raw):\n"
            "    try:\n"
            "        val = int(raw)\n"
            "        log('parsed')\n"
            "        return val\n"
            "    except ValueError:\n"
            "        log('error')\n"
            "        fallback = 0\n"
            "        return fallback\n"
        )
        result = self.service.analyze_project(make_payload(("parse.py", code)))
        self.assertEqual(result.status, "success")
        sym_names = {s.name for s in result.symbols}
        self.assertTrue({"val", "fallback"}.issubset(sym_names))
        log_calls = [c for c in result.call_references if "log(" in c.expression]
        self.assertEqual(len(log_calls), 2)
        for c in log_calls:
            self.assertEqual(c.resolution, "resolved")

    # 10. for/else and while/else
    def test_scenario_10_for_else_and_while_else(self):
        code = (
            "def find_item(items, target):\n"
            "    for x in items:\n"
            "        if x == target:\n"
            "            return True\n"
            "    else:\n"
            "        return False\n\n"
            "def drain(queue):\n"
            "    while queue:\n"
            "        item = queue.pop()\n"
            "        if item == 0:\n"
            "            break\n"
            "    else:\n"
            "        done = True\n"
        )
        result = self.service.analyze_project(make_payload(("search.py", code)))
        self.assertEqual(result.status, "success")
        self.assertFalse(any(d.code == "INCOMPLETE_SCOPE" for d in result.diagnostics))

    # 11. Nested loops
    def test_scenario_11_nested_loops(self):
        code = (
            "def nested():\n"
            "    for i in range(3):\n"
            "        for j in range(3):\n"
            "            if i == j:\n"
            "                continue\n"
            "            print(i, j)\n"
        )
        result = self.service.analyze_project(make_payload(("nested.py", code)))
        self.assertEqual(result.status, "success")
        fn_graph = result.graphs[result.functions[0].graph_id]
        links = self._graph_links(fn_graph)
        # Verify continue goes to inner loop header
        self.assertIn(("continue", "Next: j", "continue"), links)

    # 12. Infinite loop without break
    def test_scenario_12_infinite_loop_without_break(self):
        code = "def worker():\n    while True:\n        heartbeat()\n"
        result = self.service.analyze_project(make_payload(("worker.py", code)))
        self.assertEqual(result.status, "success")
        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = [n.label for n in fn_graph.nodes]
        self.assertNotIn("End", labels)
        self.assertIn("Start", labels)
        self.assertIn("heartbeat()", labels)

    # 13. Loop with reachable break
    def test_scenario_13_loop_with_reachable_break(self):
        code = (
            "def worker(stop):\n"
            "    while True:\n"
            "        if stop:\n"
            "            break\n"
            "        heartbeat()\n"
        )
        result = self.service.analyze_project(make_payload(("worker.py", code)))
        self.assertEqual(result.status, "success")
        fn_graph = result.graphs[result.functions[0].graph_id]
        labels = [n.label for n in fn_graph.nodes]
        self.assertIn("End", labels)

    # 14. Early returns
    def test_scenario_14_early_returns(self):
        code = (
            "def categorize(x):\n"
            "    if x < 0:\n"
            "        return 'negative'\n"
            "    elif x == 0:\n"
            "        return 'zero'\n"
            "    return 'positive'\n"
        )
        result = self.service.analyze_project(make_payload(("cat.py", code)))
        self.assertEqual(result.status, "success")
        fn_graph = result.graphs[result.functions[0].graph_id]
        links = self._graph_links(fn_graph)
        self.assertIn(("return 'negative'", "End", "return"), links)
        self.assertIn(("return 'zero'", "End", "return"), links)
        self.assertIn(("return 'positive'", "End", "return"), links)

    # 15. Recursive function calls
    def test_scenario_15_recursive_function_calls(self):
        code = (
            "def factorial(n):\n"
            "    if n <= 1:\n"
            "        return 1\n"
            "    return n * factorial(n - 1)\n"
        )
        result = self.service.analyze_project(make_payload(("fact.py", code)))
        self.assertEqual(result.status, "success")
        call = [c for c in result.call_references if "factorial" in c.expression][0]
        self.assertEqual(call.resolution, "resolved")
        self.assertEqual(call.target_function_id, result.functions[0].function_id)

    # 16. Cross-file function calls
    def test_scenario_16_cross_file_function_calls(self):
        lib = "def greet(name):\n    return 'Hello, ' + name\n"
        app = "from lib import greet\ndef main():\n    return greet('World')\n"
        result = self.service.analyze_project(make_payload(("lib.py", lib), ("app.py", app)))
        self.assertEqual(result.status, "success")
        greet_fn = [f for f in result.functions if f.function_name == "greet"][0]
        call = [c for c in result.call_references if "greet(" in c.expression][0]
        self.assertEqual(call.resolution, "resolved")
        self.assertEqual(call.target_function_id, greet_fn.function_id)

    # 17. Unsupported classes
    def test_scenario_17_unsupported_classes(self):
        code = "class Student:\n    def __init__(self, name):\n        self.name = name\n"
        result = self.service.analyze_project(make_payload(("student.py", code)))
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(d.code == "UNSUPPORTED_FEATURE" and "ClassDef" in d.message for d in result.diagnostics))
        self.assertEqual(result.files[0].status, "unsupported")

    # 18. Unsupported async constructs
    def test_scenario_18_unsupported_async(self):
        code = "async def fetch():\n    await task()\n"
        result = self.service.analyze_project(make_payload(("async_demo.py", code)))
        self.assertEqual(result.status, "partial")
        self.assertTrue(any(d.code == "UNSUPPORTED_FEATURE" for d in result.diagnostics))

    # 19. Unsupported dynamic evaluation
    def test_scenario_19_unsupported_dynamic_evaluation(self):
        code1 = "x = eval('2 + 2')\n"
        res1 = self.service.analyze_project(make_payload(("eval.py", code1)))
        self.assertEqual(res1.status, "partial")
        self.assertTrue(any("eval()" in d.message for d in res1.diagnostics))

        code2 = "exec('x = 1')\n"
        res2 = self.service.analyze_project(make_payload(("exec.py", code2)))
        self.assertEqual(res2.status, "partial")
        self.assertTrue(any("exec()" in d.message for d in res2.diagnostics))

    # 20. Invalid Python syntax
    def test_scenario_20_invalid_python_syntax(self):
        bad_src = "def ! invalid syntax\n"
        good_src = "def f():\n    return 42\n"
        result = self.service.analyze_project(make_payload(("bad.py", bad_src), ("good.py", good_src)))
        self.assertEqual(result.status, "partial")
        # bad.py should fail with SYNTAX_ERROR
        bad_file = [f for f in result.files if f.file_name == "bad.py"][0]
        self.assertEqual(bad_file.status, "failed")
        self.assertTrue(any(d.code == "SYNTAX_ERROR" and d.file_id == bad_file.file_id for d in result.diagnostics))
        # good.py should succeed
        good_file = [f for f in result.files if f.file_name == "good.py"][0]
        self.assertEqual(good_file.status, "complete")
        self.assertEqual(len(result.functions), 1)

    # 21. Project/File/Function graph navigation
    def test_scenario_21_graph_navigation_references(self):
        code = (
            "def foo():\n    return 1\n\n"
            "x = foo()\n"
        )
        result = self.service.analyze_project(make_payload(("nav.py", code)))
        self.assertEqual(result.status, "success")
        refs = result.graph_references

        # Project -> File reference
        proj_to_file = [r for r in refs if r.source_graph_id == result.graphs[list(result.graphs.keys())[0]].graph_id]
        self.assertTrue(len(refs) >= 3)

        # File graph references foo function graph and module execution graph
        file_graph = result.graphs[result.files[0].graph_id]
        targets_from_file = {r.target_graph_id for r in refs if r.source_graph_id == file_graph.graph_id}
        self.assertIn(result.functions[0].graph_id, targets_from_file)

        # Module execution graph references foo function graph from def foo(...)
        mod_graph = [g for g in result.graphs.values() if g.graph_type == "module"][0]
        targets_from_mod = {r.target_graph_id for r in refs if r.source_graph_id == mod_graph.graph_id}
        self.assertIn(result.functions[0].graph_id, targets_from_mod)

    # 22. Source-code extraction using function source locations
    def test_scenario_22_source_code_extraction(self):
        code = (
            "# Top comment\n"
            "def my_func(a, b):\n"
            "    c = a + b\n"
            "    return c\n"
            "\n"
            "x = 10\n"
        )
        result = self.service.analyze_project(make_payload(("slice.py", code)))
        self.assertEqual(result.status, "success")
        fn = result.functions[0]

        # Extract using 1-based start_line to end_line
        lines = code.splitlines()
        extracted = "\n".join(lines[fn.start_line - 1 : fn.end_line])
        expected = "def my_func(a, b):\n    c = a + b\n    return c"
        self.assertEqual(extracted, expected)

    # 23. Backend API upload and analysis contract
    def test_scenario_23_backend_output_contracts(self):
        code = "def add(a, b):\n    return a + b\n\nx = add(1, 2)\n"
        result = self.service.analyze_project(make_payload(("app.py", code)))
        fc = FlowchartOutput(result).to_dict()
        mp = MappingOutput(result).to_dict()

        # Contract checks
        self.assertIn("revisionId", fc)
        self.assertIn("files", fc)
        self.assertIn("functions", fc)
        self.assertIn("graphs", fc)
        self.assertIn("graphReferences", fc)
        self.assertIn("symbols", fc)

        self.assertIn("sourceMappings", mp)
        self.assertIn("callReferences", mp)

        # JSON serialization check
        json_fc = json.loads(FlowchartOutput(result).to_json())
        json_mp = json.loads(MappingOutput(result).to_json())
        self.assertEqual(json_fc["revisionId"], 1)
        self.assertEqual(json_mp["revisionId"], 1)

    # 24. Graph reachability, edge endpoints, and source mappings integrity
    def test_scenario_24_graph_integrity_and_mapping_coverage(self):
        code = (
            "def calc(n):\n"
            "    total = 0\n"
            "    for i in range(n):\n"
            "        if i % 2 == 0:\n"
            "            total += i\n"
            "        else:\n"
            "            continue\n"
            "    return total\n"
            "\n"
            "print(calc(10))\n"
        )
        result = self.service.analyze_project(make_payload(("integ.py", code)))
        self.assertEqual(result.status, "success")

        # 1-to-1 mapping coverage: every node with source location has exactly one mapping
        expected_mappings = {
            (g.graph_id, n.node_id)
            for g in result.graphs.values()
            for n in g.nodes
            if n.source_location is not None
        }
        actual_mappings = {(m.graph_id, m.node_id) for m in result.source_mappings}
        self.assertEqual(expected_mappings, actual_mappings)

        # Every edge endpoint must exist in the owning graph
        for g in result.graphs.values():
            node_ids = {n.node_id for n in g.nodes}
            for e in g.edges:
                self.assertIn(e.source_id, node_ids)
                self.assertIn(e.target_id, node_ids)
