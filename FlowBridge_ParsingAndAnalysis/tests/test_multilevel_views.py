"""Tests for Multi-Level Views: Project View, File View, and Function View.
Verifies file-level dependency edges, file-level execution CFGs with same-file
inlining, cross-file call links, recursion guards, and source mapping integrity.
"""
import unittest
from flowbridge_analysis import ParsingAnalysisService, FlowchartOutput, MappingOutput
from test_pipeline import payload


class MultiLevelViewsTests(unittest.TestCase):
    def setUp(self):
        self.service = ParsingAnalysisService()

    def test_project_view_import_edges(self):
        calc_code = "def add(a, b):\n    return a + b\n"
        fmt_code = "def format_result(x):\n    return f'Ans: {x}'\n"
        main_code = (
            "from calculator import add\n"
            "from formatter import format_result\n"
            "x = 10\n"
            "y = 20\n"
            "res = add(x, y)\n"
            "print(format_result(res))\n"
        )
        standalone_code = "z = 999\n"

        result = self.service.analyze_project(payload(
            ('calculator.py', calc_code),
            ('formatter.py', fmt_code),
            ('main.py', main_code),
            ('standalone.py', standalone_code),
        ))
        self.assertEqual(result.status, 'success')

        project_graph = next(g for g in result.graphs.values() if g.graph_type == 'project')
        self.assertEqual(len(project_graph.nodes), 4)

        # File ID mapping
        file_by_name = {f.file_name: f.file_id for f in result.files}
        main_id = file_by_name['main.py']
        calc_id = file_by_name['calculator.py']
        fmt_id = file_by_name['formatter.py']
        standalone_id = file_by_name['standalone.py']

        # Node ID mapping in project graph
        node_id_to_file = {}
        for ref in result.graph_references:
            if ref.source_graph_id == project_graph.graph_id:
                # Find matching file metadata
                matching_file = next(f for f in result.files if f.graph_id == ref.target_graph_id)
                node_id_to_file[ref.source_node_id] = matching_file.file_id

        # Verify edges connect main.py -> calculator.py and main.py -> formatter.py
        edge_pairs = {
            (node_id_to_file[e.source_id], node_id_to_file[e.target_id])
            for e in project_graph.edges
        }
        self.assertIn((main_id, calc_id), edge_pairs)
        self.assertIn((main_id, fmt_id), edge_pairs)

        # Standalone file should have no incoming or outgoing edges
        for src, tgt in edge_pairs:
            self.assertNotEqual(src, standalone_id)
            self.assertNotEqual(tgt, standalone_id)

    def test_file_view_definitions_and_navigation(self):
        code = (
            "def add(a, b):\n"
            "    return a + b\n\n"
            "def multiply(a, b):\n"
            "    return a * b\n"
        )
        result = self.service.analyze_project(payload(('calc.py', code)))
        self.assertEqual(result.status, 'success')

        file_graph = result.graphs[result.files[0].graph_id]
        self.assertEqual(file_graph.graph_type, 'file')

        labels = [n.label for n in file_graph.nodes]
        self.assertEqual(set(labels), {'Start', 'add', 'multiply', 'End'})

        # Check edges: Start -> add -> multiply -> End
        label_map = {n.node_id: n.label for n in file_graph.nodes}
        edge_chain = [(label_map[e.source_id], label_map[e.target_id]) for e in file_graph.edges]
        self.assertIn(('Start', 'add'), edge_chain)
        self.assertIn(('add', 'multiply'), edge_chain)
        self.assertIn(('multiply', 'End'), edge_chain)

        # Function references exist
        fn_refs = {r.source_node_id: r.target_graph_id for r in result.graph_references
                   if r.source_graph_id == file_graph.graph_id}
        add_node = next(n for n in file_graph.nodes if n.label == 'add')
        mul_node = next(n for n in file_graph.nodes if n.label == 'multiply')
        self.assertIn(add_node.node_id, fn_refs)
        self.assertIn(mul_node.node_id, fn_refs)

    def test_file_view_same_file_function_inlining(self):
        code = (
            "def calculate():\n"
            "    x = 10\n"
            "    y = 20\n"
            "    return x + y\n\n"
            "def main():\n"
            "    result = calculate()\n"
            "    print(result)\n\n"
            "main()\n"
        )
        result = self.service.analyze_project(payload(('test.py', code)))
        self.assertEqual(result.status, 'success')

        file_graph = result.graphs[result.files[0].graph_id]
        labels = [n.label for n in file_graph.nodes]

        # Verify definitions and inlined body statements exist
        self.assertIn('calculate', labels)
        self.assertIn('main', labels)
        self.assertIn('x = 10', labels)
        self.assertIn('y = 20', labels)
        self.assertIn('return x + y', labels)
        self.assertIn('print(result)', labels)

        # Verify edge continuity: return connects to print(result), which connects to End
        label_map = {n.node_id: n.label for n in file_graph.nodes}
        edges = [(label_map[e.source_id], label_map[e.target_id]) for e in file_graph.edges]
        self.assertIn(('return x + y', 'print(result)'), edges)
        self.assertIn(('print(result)', 'End'), edges)

    def test_file_view_multiple_local_calls(self):
        code = (
            "def double(n):\n"
            "    return n * 2\n\n"
            "a = double(5)\n"
            "b = double(10)\n"
        )
        result = self.service.analyze_project(payload(('multi.py', code)))
        self.assertEqual(result.status, 'success')

        file_graph = result.graphs[result.files[0].graph_id]
        return_nodes = [n for n in file_graph.nodes if n.label == 'return n * 2']
        # Expanded twice at two distinct call sites
        self.assertEqual(len(return_nodes), 2)
        self.assertNotEqual(return_nodes[0].node_id, return_nodes[1].node_id)

    def test_file_view_recursion_guard(self):
        code = (
            "def countdown(n):\n"
            "    if n <= 0:\n"
            "        return 0\n"
            "    return countdown(n - 1)\n\n"
            "countdown(5)\n"
        )
        result = self.service.analyze_project(payload(('rec.py', code)))
        self.assertEqual(result.status, 'success')

        file_graph = result.graphs[result.files[0].graph_id]
        labels = [n.label for n in file_graph.nodes]
        # Should have stopped recursion safely and emitted recursive node
        self.assertTrue(any('recursive' in l for l in labels))

    def test_file_view_cross_file_call(self):
        calc_code = "def add(a, b):\n    return a + b\n"
        main_code = (
            "from calculator import add\n\n"
            "x = 10\n"
            "y = 20\n"
            "result = add(x, y)\n"
            "print(result)\n"
        )
        result = self.service.analyze_project(payload(
            ('calculator.py', calc_code),
            ('main.py', main_code),
        ))
        self.assertEqual(result.status, 'success')

        main_file = next(f for f in result.files if f.file_name == 'main.py')
        calc_file = next(f for f in result.files if f.file_name == 'calculator.py')
        main_graph = result.graphs[main_file.graph_id]
        calc_fn = [f for f in result.functions if f.file_id == calc_file.file_id][0]

        # Call node in main_graph should reference calc_fn.graph_id
        call_node = next(n for n in main_graph.nodes if 'add(x, y)' in n.label)
        self.assertEqual(call_node.node_type, 'function')

        ref = next(r for r in result.graph_references if r.source_node_id == call_node.node_id)
        self.assertEqual(ref.source_graph_id, main_graph.graph_id)
        self.assertEqual(ref.target_graph_id, calc_fn.graph_id)

        # Incoming from y = 20, outgoing to print(result)
        label_map = {n.node_id: n.label for n in main_graph.nodes}
        edges = [(label_map[e.source_id], label_map[e.target_id]) for e in main_graph.edges]
        self.assertIn(('y = 20', call_node.label), edges)
        self.assertIn((call_node.label, 'print(result)'), edges)

    def test_file_view_builtins_and_unresolved_calls(self):
        code = (
            "print('logging')\n"
            "nonexistent_fn()\n"
        )
        result = self.service.analyze_project(payload(('misc.py', code)))
        self.assertEqual(result.status, 'success')

        file_graph = result.graphs[result.files[0].graph_id]
        labels = [n.label for n in file_graph.nodes]
        self.assertIn("print('logging')", labels)
        self.assertIn('nonexistent_fn()', labels)

    def test_kevin_and_grace_projections_compatibility(self):
        code = (
            "def compute(x):\n"
            "    return x * 2\n\n"
            "val = compute(10)\n"
            "print(val)\n"
        )
        result = self.service.analyze_project(payload(('app.py', code)))
        self.assertEqual(result.status, 'success')

        kevin = FlowchartOutput(result).to_dict()
        grace = MappingOutput(result).to_dict()

        self.assertIn('graphs', kevin)
        self.assertIn('graphReferences', kevin)
        self.assertIn('sourceMappings', grace)

        # Check source mapping integrity for every mapped node
        mapped_nodes = {m['nodeId'] for m in grace['sourceMappings']}
        for g_id, graph_dict in kevin['graphs'].items():
            for node in graph_dict['nodes']:
                if node.get('sourceLocation') is not None:
                    self.assertIn(node['nodeId'], mapped_nodes)


if __name__ == '__main__':
    unittest.main()
