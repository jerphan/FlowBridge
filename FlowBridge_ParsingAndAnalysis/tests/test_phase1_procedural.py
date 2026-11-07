"""Tests for Phase 1: Top-level procedural statements, augmented assignments,
annotated assignments, try/except scopes, and loop else traversal.
"""
import json
import unittest
from flowbridge_analysis import (ParsingAnalysisService, FlowchartOutput, MappingOutput,
                                 FeatureValidator, CFGBuilder, RevisionIds, PythonParser)
from flowbridge_analysis.models import FileInput


def make_payload(*sources):
    return {
        'projectId': 'P',
        'projectName': 'Phase1Test',
        'revisionId': 1,
        'files': [
            {'fileId': str(i), 'fileName': name, 'filePath': name, 'fileContent': src}
            for i, (name, src) in enumerate(sources)
        ]
    }


class Phase1ProceduralTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def test_pure_procedural_script(self):
        code = "x = 10\ny = 20\nprint(x + y)\n"
        result = self.service.analyze_project(make_payload(('script.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        # File graph exists and has 1 node for script execution
        file_graph = result.graphs[result.files[0].graph_id]
        self.assertEqual(file_graph.graph_type, 'file')
        self.assertEqual(len(file_graph.nodes), 1)
        self.assertEqual(file_graph.nodes[0].label, 'script.py execution')

        # Module graph exists and is complete
        mod_graph_id = [ref.target_graph_id for ref in result.graph_references
                        if ref.source_graph_id == file_graph.graph_id][0]
        mod_graph = result.graphs[mod_graph_id]
        self.assertEqual(mod_graph.graph_type, 'module')
        self.assertEqual(mod_graph.status, 'complete')

        # Check nodes: Start, x = 10, y = 20, print(x + y), End
        labels = [n.label for n in mod_graph.nodes]
        self.assertIn('Start', labels)
        self.assertIn('x = 10', labels)
        self.assertIn('y = 20', labels)
        self.assertIn('print(x + y)', labels)
        self.assertIn('End', labels)

        # Verify edges exist connecting Start -> stmts -> End
        self.assertTrue(len(mod_graph.edges) >= 4)

        # Verify symbols
        symbol_names = [s.name for s in result.symbols]
        self.assertIn('x', symbol_names)
        self.assertIn('y', symbol_names)

        # Verify flowchart and mapping serialization
        fc = FlowchartOutput(result).to_dict()
        mp = MappingOutput(result).to_dict()
        self.assertIn(mod_graph_id, fc['graphs'])
        self.assertEqual(fc['graphs'][mod_graph_id]['graphType'], 'module')

    def test_function_definition_and_module_call(self):
        code = (
            "def add(a, b):\n"
            "    return a + b\n"
            "\n"
            "x = add(2, 3)\n"
        )
        result = self.service.analyze_project(make_payload(('main.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.functions), 1)
        self.assertEqual(result.functions[0].function_name, 'add')

        # Call reference from module level resolves to add function
        self.assertEqual(len(result.call_references), 1)
        call = result.call_references[0]
        self.assertEqual(call.expression, 'add(2, 3)')
        self.assertEqual(call.resolution, 'resolved')
        self.assertEqual(call.target_function_id, result.functions[0].function_id)
        self.assertEqual(call.target_graph_id, result.functions[0].graph_id)

        # File graph has nodes for both 'add' and 'main.py execution'
        file_graph = result.graphs[result.files[0].graph_id]
        self.assertEqual(len(file_graph.nodes), 2)
        node_labels = {n.label for n in file_graph.nodes}
        self.assertIn('add', node_labels)
        self.assertIn('main.py execution', node_labels)

        # Module graph has def add(...) statement with reference to function graph
        mod_graph = [g for g in result.graphs.values() if g.graph_type == 'module'][0]
        mod_labels = [n.label for n in mod_graph.nodes]
        self.assertIn('def add(...)', mod_labels)
        self.assertIn('x = add(2, 3)', mod_labels)
        # Function body should NOT be inlined into module graph
        self.assertNotIn('return a + b', mod_labels)

        # Check graph reference from module's def add node to add's function graph
        def_node_id = [n.node_id for n in mod_graph.nodes if n.label == 'def add(...)'][0]
        self.assertTrue(any(
            ref.source_graph_id == mod_graph.graph_id and
            ref.source_node_id == def_node_id and
            ref.target_graph_id == result.functions[0].graph_id
            for ref in result.graph_references
        ))

    def test_augmented_and_annotated_assignments(self):
        code = (
            "total: int = 0\n"
            "total += 10\n"
            "def accumulate(val: int) -> int:\n"
            "    count: int = val\n"
            "    count += 5\n"
            "    return count\n"
        )
        result = self.service.analyze_project(make_payload(('assigns.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        # Check symbols include total and count
        names = {s.name for s in result.symbols}
        self.assertIn('total', names)
        self.assertIn('count', names)

        # Check module graph has the assignments
        mod_graph = [g for g in result.graphs.values() if g.graph_type == 'module'][0]
        mod_labels = [n.label for n in mod_graph.nodes]
        self.assertIn('total: int = 0', mod_labels)
        self.assertIn('total += 10', mod_labels)

        # Check function graph has the assignments
        fn_graph = result.graphs[result.functions[0].graph_id]
        fn_labels = [n.label for n in fn_graph.nodes]
        self.assertIn('count: int = val', fn_labels)
        self.assertIn('count += 5', fn_labels)

    def test_try_except_scope_completeness(self):
        code = (
            "def safe_calc(a, b):\n"
            "    try:\n"
            "        result = a / b\n"
            "    except ZeroDivisionError:\n"
            "        result = 0\n"
            "    return result\n"
        )
        result = self.service.analyze_project(make_payload(('safe.py', code)))
        self.assertEqual(result.status, 'success')
        # No INCOMPLETE_SCOPE warnings
        self.assertFalse(any(d.code == 'INCOMPLETE_SCOPE' for d in result.diagnostics))

        fn_graph = result.graphs[result.functions[0].graph_id]
        self.assertEqual(fn_graph.status, 'complete')

    def test_loop_else_traversal(self):
        code = (
            "def search(items, target):\n"
            "    for item in items:\n"
            "        if item == target:\n"
            "            found = True\n"
            "            break\n"
            "    else:\n"
            "        found = False\n"
            "    return found\n"
        )
        result = self.service.analyze_project(make_payload(('search.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertFalse(any(d.code == 'INCOMPLETE_SCOPE' for d in result.diagnostics))

        # Check that 'found' is recognized as a symbol
        names = {s.name for s in result.symbols}
        self.assertIn('found', names)

    def test_module_level_loops_and_conditionals(self):
        code = (
            "n = 5\n"
            "if n > 0:\n"
            "    sign = 1\n"
            "else:\n"
            "    sign = -1\n"
            "\n"
            "for i in range(n):\n"
            "    print(i)\n"
        )
        result = self.service.analyze_project(make_payload(('control.py', code)))
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.diagnostics), 0)

        mod_graph = [g for g in result.graphs.values() if g.graph_type == 'module'][0]
        labels = [n.label for n in mod_graph.nodes]
        self.assertIn('n = 5', labels)
        self.assertIn('n > 0', labels)
        self.assertIn('sign = 1', labels)
        self.assertIn('sign = -1', labels)
        self.assertIn('Iterate: range(n)', labels)
        self.assertIn('print(i)', labels)

    def test_unsupported_features_still_rejected(self):
        # Classes, async, yield, eval must still produce error diagnostics
        sources = [
            "class MyClass:\n    pass\n",
            "async def my_coro():\n    pass\n",
            "def gen():\n    yield 1\n",
            "return 42\n",
        ]
        for src in sources:
            with self.subTest(src=src):
                result = self.service.analyze_project(make_payload(('test.py', src)))
                self.assertIn(result.status, ('partial', 'failed'))
                self.assertTrue(any(d.code == 'UNSUPPORTED_FEATURE' for d in result.diagnostics))
