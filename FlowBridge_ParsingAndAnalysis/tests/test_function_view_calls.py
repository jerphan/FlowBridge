"""Tests for Function View Call Node Architecture & Drill-Down Navigation (Phase 3)."""
import unittest
from flowbridge_analysis import ParsingAnalysisService, FlowchartOutput, MappingOutput
from test_pipeline import payload


class FunctionViewCallsTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def test_same_file_function_view_call_node_and_drill_down(self):
        code = (
            "def add(a, b):\n"
            "    return a + b\n\n"
            "def main():\n"
            "    result = add(5, 4)\n"
            "    print(result)\n\n"
            "main()\n"
        )
        res = self.service.analyze_project(payload(('main.py', code)))
        self.assertEqual(res.status, 'success')

        add_fn = next(f for f in res.functions if f.function_name == 'add')
        main_fn = next(f for f in res.functions if f.function_name == 'main')

        main_graph = res.graphs[main_fn.graph_id]
        self.assertEqual(main_graph.graph_type, 'function')

        # Find the call node inside main()
        call_node = next((n for n in main_graph.nodes if 'add(5, 4)' in n.label), None)
        self.assertIsNotNone(call_node)
        self.assertEqual(call_node.node_type, 'function')

        # Verify GraphReference exists linking main's call node to add's graph
        call_ref = next((r for r in res.graph_references
                         if r.source_graph_id == main_graph.graph_id and r.source_node_id == call_node.node_id), None)
        self.assertIsNotNone(call_ref)
        self.assertEqual(call_ref.target_graph_id, add_fn.graph_id)

        # Source mapping points to the call site in main.py, not add's definition
        self.assertEqual(call_node.source_location.start_line, 5)

    def test_cross_file_function_view_call_node(self):
        calc_code = "def add(a, b):\n    return a + b\n"
        main_code = (
            "from calculator import add\n\n"
            "def compute():\n"
            "    return add(5, 4)\n"
        )
        res = self.service.analyze_project(payload(
            ('calculator.py', calc_code),
            ('main.py', main_code),
        ))
        self.assertEqual(res.status, 'success')

        calc_file = next(f for f in res.files if f.file_name == 'calculator.py')
        main_file = next(f for f in res.files if f.file_name == 'main.py')

        calc_fn = next(f for f in res.functions if f.file_id == calc_file.file_id)
        comp_fn = next(f for f in res.functions if f.file_id == main_file.file_id)

        comp_graph = res.graphs[comp_fn.graph_id]
        call_node = next((n for n in comp_graph.nodes if 'add(5, 4)' in n.label), None)
        self.assertIsNotNone(call_node)
        self.assertEqual(call_node.node_type, 'function')

        # GraphReference points to calc_fn in calculator.py
        ref = next((r for r in res.graph_references
                    if r.source_graph_id == comp_graph.graph_id and r.source_node_id == call_node.node_id), None)
        self.assertIsNotNone(ref)
        self.assertEqual(ref.target_graph_id, calc_fn.graph_id)

        # Source location of call node is in main.py
        self.assertEqual(call_node.source_location.file_id, main_file.file_id)
        self.assertEqual(call_node.source_location.start_line, 4)

    def test_nested_calls_evaluation_order(self):
        code = (
            "def add(a, b):\n"
            "    return a + b\n\n"
            "def subtract(a, b):\n"
            "    return a - b\n\n"
            "def multiply(a, b):\n"
            "    return a * b\n\n"
            "def compute():\n"
            "    result = multiply(add(2, 3), subtract(10, 4))\n"
            "    return result\n"
        )
        res = self.service.analyze_project(payload(('math_test.py', code)))
        self.assertEqual(res.status, 'success')

        comp_fn = next(f for f in res.functions if f.function_name == 'compute')
        comp_graph = res.graphs[comp_fn.graph_id]

        labels = [n.label for n in comp_graph.nodes]
        self.assertIn('add(2, 3)', labels)
        self.assertIn('subtract(10, 4)', labels)
        self.assertTrue(any('multiply' in l for l in labels))

        add_node = next(n for n in comp_graph.nodes if n.label == 'add(2, 3)')
        sub_node = next(n for n in comp_graph.nodes if n.label == 'subtract(10, 4)')
        mul_node = next(n for n in comp_graph.nodes if 'multiply' in n.label)

        # Check edge continuity: add -> subtract -> multiply
        label_map = {n.node_id: n.label for n in comp_graph.nodes}
        edge_pairs = [(label_map[e.source_id], label_map[e.target_id]) for e in comp_graph.edges]
        self.assertIn((add_node.label, sub_node.label), edge_pairs)
        self.assertIn((sub_node.label, mul_node.label), edge_pairs)


if __name__ == '__main__':
    unittest.main()
