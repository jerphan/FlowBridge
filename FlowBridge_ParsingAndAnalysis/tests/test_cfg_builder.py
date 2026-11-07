"""Graph topology, terminal paths and mapping integrity tests."""
import unittest

from flowbridge_analysis import ASTAnalyzer, PythonParser, RevisionIds
from flowbridge_analysis.CFGBuilder import CFGBuilder
from flowbridge_analysis.models import FileInput


def build(source, revision=1):
    file = FileInput(file_id='F', file_name='f.py', file_path='f.py', file_content=source)
    tree = PythonParser().parse(file).tree
    if tree is None:
        raise AssertionError('Test source must parse')
    return CFGBuilder().build(tree.body[0], file, RevisionIds('P', revision))


def node(result, label):
    return next(item for item in result.graph.nodes if item.label == label)


def links(result):
    labels = {item.node_id: item.label for item in result.graph.nodes}
    return {(labels[edge.source_id], labels[edge.target_id], edge.edge_type) for edge in result.graph.edges}


class BasicCFGTests(unittest.TestCase):
    def test_sequence(self):
        result = build('def f():\n    x = 1\n    print(x)\n    return x')
        self.assertEqual(links(result), {('Start', 'x = 1', 'next'), ('x = 1', 'print(x)', 'next'),
                                       ('print(x)', 'return x', 'next'), ('return x', 'End', 'return')})

    def test_if_else_joins(self):
        result = build('def f(x):\n    if x:\n        y = 1\n    else:\n        y = 2\n    return y')
        self.assertIn(('x', 'y = 1', 'true'), links(result))
        self.assertIn(('x', 'y = 2', 'false'), links(result))
        self.assertIn(('y = 1', 'return y', 'next'), links(result))
        self.assertIn(('y = 2', 'return y', 'next'), links(result))

    def test_missing_else_and_pass_branch(self):
        result = build('def f(x):\n    if x:\n        pass\n    return 2')
        self.assertEqual(result.graph.status, 'complete')
        self.assertIn(('x', 'return 2', 'false'), links(result))
        self.assertIn(('pass', 'return 2', 'next'), links(result))

    def test_elif_and_nested_branch(self):
        result = build('def f(x, y):\n    if x:\n        if y:\n            return 1\n'
                       '    elif y:\n        return 2\n    else:\n        return 3\n    return 4')
        labels = links(result)
        self.assertIn(('y', 'return 4', 'false'), labels)
        self.assertNotIn(('return 1', 'return 4', 'next'), labels)
        self.assertEqual(sum(n.node_type == 'condition' for n in result.graph.nodes), 3)

    def test_all_paths_return_omit_following_statement(self):
        result = build('def f(x):\n    if x:\n        return 1\n    else:\n        return 2\n    dead()')
        self.assertNotIn('dead()', [n.label for n in result.graph.nodes])
        self.assertEqual(result.diagnostics[0].code, 'UNREACHABLE_STATEMENT')
        self.assertEqual(result.diagnostics[0].source_location.start_line, 6)

    def test_single_branch_return_does_not_join(self):
        result = build('def f(x):\n    if x:\n        return 1\n    live()\n    return 2')
        self.assertIn(('x', 'live()', 'false'), links(result))
        self.assertEqual([e.edge_type for e in result.graph.edges if e.source_id == node(result, 'return 1').node_id], ['return'])

    def test_implicit_return_and_empty_function(self):
        result = build('def f():\n    pass')
        self.assertIn(('pass', 'End', 'next'), links(result))

    def test_unreachable_unsupported_construct_rejects_entire_graph(self):
        result = build('def f():\n    return 1\n    with resource():\n        pass')
        self.assertEqual(result.graph.status, 'unsupported')
        self.assertEqual(result.graph.nodes, [])
        self.assertEqual(result.source_mappings, [])

    def test_ids_match_metadata_and_are_deterministic(self):
        source = 'def f():\n    return 1'
        first, second = build(source), build(source)
        self.assertEqual(first.graph.to_json(), second.graph.to_json())
        self.assertNotEqual(first.graph.graph_id, build(source, 2).graph.graph_id)
        file = FileInput(file_id='F', file_name='f.py', file_path='f.py', file_content=source)
        metadata = ASTAnalyzer().analyze(PythonParser().parse(file).tree, file, RevisionIds('P', 1))
        self.assertEqual(first.graph.graph_id, metadata.functions[0].graph_id)
        self.assertEqual(first.graph.function_id, metadata.functions[0].function_id)

    def test_source_positions_and_integrity(self):
        result = build('def f(é):\n    if é:\n        return é\n    return 0')
        nodes = {n.node_id: n for n in result.graph.nodes}
        self.assertEqual(len(nodes), len(result.graph.nodes))
        self.assertEqual(len({e.edge_id for e in result.graph.edges}), len(result.graph.edges))
        for edge in result.graph.edges:
            self.assertIn(edge.source_id, nodes)
            self.assertIn(edge.target_id, nodes)
        for mapping in result.source_mappings:
            self.assertEqual(mapping.location, nodes[mapping.node_id].source_location)
            self.assertEqual(mapping.graph_id, result.graph.graph_id)
        self.assertEqual(len(result.source_mappings), sum(n.source_location is not None for n in nodes.values()))
        self.assertEqual(node(result, 'é').source_location.start_column, 7)
        self.assertEqual(node(result, 'é').source_location.end_column, 9)


class LoopCFGTests(unittest.TestCase):
    def test_while_back_and_false_exit(self):
        result = build('def f(x):\n    while x:\n        tick()\n    done()')
        self.assertIn(('x', 'tick()', 'true'), links(result))
        self.assertIn(('Loop back', 'x', 'back'), links(result))
        self.assertIn(('x', 'done()', 'false'), links(result))

    def test_for_initializes_iterator_once(self):
        result = build('def f(xs):\n    for x in source(xs):\n        use(x)\n    done()')
        self.assertIn(('Iterate: source(xs)', 'Next: x', 'next'), links(result))
        self.assertIn(('Loop back', 'Next: x', 'back'), links(result))
        self.assertIn(('Next: x', 'done()', 'false'), links(result))
        setup = node(result, 'Iterate: source(xs)').node_id
        self.assertEqual(sum(e.target_id == setup for e in result.graph.edges), 1)

    def test_break_and_continue_terminate_their_paths(self):
        result = build('def f(xs):\n    for x in xs:\n        if x:\n            break\n'
                       '        else:\n            continue\n        dead()\n    done()')
        self.assertIn(('break', 'done()', 'break'), links(result))
        self.assertIn(('continue', 'Next: x', 'continue'), links(result))
        self.assertNotIn('dead()', [n.label for n in result.graph.nodes])
        self.assertNotIn('Loop back', [n.label for n in result.graph.nodes])

    def test_nested_loops_target_nearest_context(self):
        result = build('def f(xs, ys):\n    for x in xs:\n        for y in ys:\n            if y:\n'
                       '                continue\n            break\n        after_inner()\n    done()')
        self.assertIn(('continue', 'Next: y', 'continue'), links(result))
        self.assertIn(('break', 'after_inner()', 'break'), links(result))
        self.assertNotIn(('break', 'done()', 'break'), links(result))

    def test_return_in_loop_has_no_back_edge(self):
        result = build('def f(xs):\n    for x in xs:\n        return x\n    return 0')
        edges = [e for e in result.graph.edges if e.source_id == node(result, 'return x').node_id]
        self.assertEqual([(e.target_id, e.edge_type) for e in edges], [(node(result, 'End').node_id, 'return')])
        self.assertIn(('Next: x', 'return 0', 'false'), links(result))

    def test_literal_true_loop_has_no_impossible_false_exit(self):
        result = build('def f():\n    while True:\n        continue\n    dead()')
        self.assertNotIn('dead()', [n.label for n in result.graph.nodes])
        self.assertNotIn(('True', 'End', 'false'), links(result))
        self.assertIn(('continue', 'True', 'continue'), links(result))

    def test_literal_false_body_and_literal_true_break(self):
        false = build('def f():\n    while False:\n        dead()\n    done()')
        self.assertNotIn('dead()', [n.label for n in false.graph.nodes])
        self.assertIn(('False', 'done()', 'false'), links(false))
        true = build('def f():\n    while True:\n        break\n    done()')
        self.assertIn(('break', 'done()', 'break'), links(true))

    def test_empty_loop_and_branch_preserve_predicate_edges(self):
        result = build('def f(x):\n    while x:\n        if x > 1:\n            continue')
        self.assertIn(('x > 1', 'Loop back', 'false'), links(result))
        self.assertIn(('Loop back', 'x', 'back'), links(result))
        self.assertEqual(build('def f(xs):\n    for x in xs:\n        pass').graph.status, 'complete')

    def test_outside_break_continue_are_rejected(self):
        for source in ['def f():\n    break', 'def f():\n    continue']:
            with self.subTest(source=source):
                result = build(source)
                self.assertEqual(result.graph.status, 'unsupported')
                self.assertEqual(result.graph.nodes, [])


class ExceptionCFGTests(unittest.TestCase):
    def test_normal_completion_bypasses_ordered_handlers(self):
        result = build('def f():\n    try:\n        work()\n    except ValueError:\n        recover()\n'
                       '    except TypeError:\n        repair()\n    done()')
        edges = links(result)
        self.assertEqual(result.graph.status, 'complete')
        self.assertIn(('work()', 'done()', 'next'), edges)
        self.assertIn(('work()', 'Exception dispatch', 'exception'), edges)
        self.assertIn(('except ValueError', 'recover()', 'true'), edges)
        self.assertIn(('except ValueError', 'except TypeError', 'false'), edges)
        self.assertIn(('except TypeError', 'Unhandled exception', 'false'), edges)
        self.assertIn(('Unhandled exception', 'Exceptional End', 'unhandled'), edges)
        self.assertIn(('recover()', 'done()', 'next'), edges)
        self.assertTrue(any(d.code == 'CONSERVATIVE_EXCEPTIONS' for d in result.diagnostics))

    def test_handler_failures_do_not_enter_sibling_handlers(self):
        result = build('def f():\n    try:\n        work()\n    except ValueError:\n        recover()\n'
                       '    except:\n        fallback()')
        self.assertIn(('recover()', 'Exceptional End', 'exception'), links(result))
        self.assertNotIn(('recover()', 'Exception dispatch', 'exception'), links(result))
        self.assertNotIn('Unhandled exception', [n.label for n in result.graph.nodes])

    def test_return_expression_can_raise_but_return_transfer_is_terminal(self):
        result = build('def f():\n    try:\n        return compute()\n        dead()\n'
                       '    except ValueError:\n        recover()\n    done()')
        self.assertIn(('Evaluate return: compute()', 'Exception dispatch', 'exception'), links(result))
        self.assertIn(('Evaluate return: compute()', 'return compute()', 'next'), links(result))
        self.assertEqual([(e.edge_type, e.target_id) for e in result.graph.edges
                          if e.source_id == node(result, 'return compute()').node_id],
                         [('return', node(result, 'End').node_id)])
        self.assertIn(('recover()', 'done()', 'next'), links(result))
        self.assertNotIn('dead()', [n.label for n in result.graph.nodes])

    def test_all_normal_and_handler_paths_return(self):
        result = build('def f():\n    try:\n        return compute()\n    except:\n        return fallback()\n    dead()')
        self.assertNotIn('dead()', [n.label for n in result.graph.nodes])
        self.assertIn(('Evaluate return: fallback()', 'Exceptional End', 'exception'), links(result))
        self.assertNotIn(('Evaluate return: fallback()', 'Exception dispatch', 'exception'), links(result))

    def test_no_raise_pass_body_omits_handler_and_does_not_reuse_ids(self):
        result = build('def f():\n    try:\n        pass\n    except:\n        dead()\n    live()')
        self.assertNotIn('dead()', [n.label for n in result.graph.nodes])
        self.assertEqual(len(result.graph.nodes), len({n.node_id for n in result.graph.nodes}))
        self.assertIn(('pass', 'live()', 'next'), links(result))
        self.assertTrue(any(d.code == 'UNREACHABLE_HANDLER' for d in result.diagnostics))

    def test_try_inside_loop_break_and_continue_keep_loop_targets(self):
        result = build('def f(xs):\n    for x in xs:\n        try:\n            work(x)\n            break\n'
                       '        except ValueError:\n            continue\n        dead()\n    done()')
        self.assertIn(('break', 'done()', 'break'), links(result))
        self.assertIn(('continue', 'Next: x', 'continue'), links(result))
        self.assertNotIn('dead()', [n.label for n in result.graph.nodes])
        self.assertNotIn(('Next: x', 'Exceptional End', 'exception'), links(result))
        self.assertNotIn(('done()', 'Exceptional End', 'exception'), links(result))

    def test_loop_inside_try_routes_setup_and_next_exceptions(self):
        result = build('def f(xs):\n    try:\n        for x in source(xs):\n            use(x)\n'
                       '    except:\n        recover()\n    done()')
        self.assertIn(('Iterate: source(xs)', 'Exception dispatch', 'exception'), links(result))
        self.assertIn(('Next: x', 'Exception dispatch', 'exception'), links(result))
        self.assertIn(('Next: x', 'done()', 'false'), links(result))

    def test_sibling_try_blocks_do_not_reuse_dispatch_context(self):
        result = build('def f():\n    try:\n        first()\n    except:\n        fix_first()\n'
                       '    try:\n        second()\n    except:\n        fix_second()')
        dispatches = [n.node_id for n in result.graph.nodes if n.node_type == 'exceptionDispatch']
        self.assertEqual(len(dispatches), 2)
        first = node(result, 'first()').node_id
        second = node(result, 'second()').node_id
        self.assertIn((first, dispatches[0]), [(e.source_id, e.target_id) for e in result.graph.edges])
        self.assertIn((second, dispatches[1]), [(e.source_id, e.target_id) for e in result.graph.edges])

    def test_unsupported_exception_semantics_fail_closed(self):
        sources = [
            'def f():\n    try:\n        work()\n    finally:\n        cleanup()',
            'def f():\n    try:\n        work()\n    except:\n        pass\n    else:\n        success()',
            'def f():\n    try:\n        work()\n    except Exception as error:\n        recover(error)',
            'def f():\n    try:\n        work()\n    except factory():\n        pass',
            'def f():\n    try:\n        try:\n            work()\n        except:\n            pass\n    except:\n        pass',
            'def f():\n    try:\n        work()\n    except* Exception:\n        pass',
            'def f():\n    try:\n        raise ValueError()\n    except:\n        pass',
        ]
        for source in sources:
            with self.subTest(source=source):
                result = build(source)
                self.assertEqual(result.graph.status, 'unsupported')
                self.assertEqual(result.graph.nodes, [])
                self.assertEqual(result.graph.edges, [])
                self.assertEqual(result.source_mappings, [])
                self.assertTrue(all(d.graph_id == result.graph.graph_id for d in result.diagnostics))

    def test_bare_return_in_try_has_no_fallthrough_or_exception(self):
        result = build('def f():\n    try:\n        return\n    except:\n        dead()\n    also_dead()')
        self.assertEqual(links(result), {('Start', 'return', 'next'), ('return', 'End', 'return')})
        self.assertNotIn('dead()', [n.label for n in result.graph.nodes])


class CFGIntegrationTests(unittest.TestCase):
    def test_full_graph_invariants_with_loops_and_exceptions(self):
        result = build('def f(xs):\n    for x in xs:\n        try:\n            if x:\n                return action(x)\n'
                       '            continue\n        except (ValueError, TypeError):\n            break\n    return 0')
        self.assertEqual(result.graph.status, 'complete')
        nodes = {n.node_id: n for n in result.graph.nodes}
        self.assertEqual(len(nodes), len(result.graph.nodes))
        self.assertEqual(len({e.edge_id for e in result.graph.edges}), len(result.graph.edges))
        for edge in result.graph.edges:
            self.assertIn(edge.source_id, nodes)
            self.assertIn(edge.target_id, nodes)
            if nodes[edge.source_id].node_type == 'return':
                self.assertEqual(edge.edge_type, 'return')
                self.assertEqual(nodes[edge.target_id].label, 'End')
            if nodes[edge.source_id].node_type in ('break', 'continue'):
                self.assertEqual(edge.edge_type, nodes[edge.source_id].node_type)
        mapped = {m.node_id for m in result.source_mappings}
        self.assertEqual(mapped, {n.node_id for n in nodes.values() if n.source_location is not None})
        for mapping in result.source_mappings:
            self.assertEqual(mapping.location, nodes[mapping.node_id].source_location)
        result.graph.to_json()

    def test_builder_reuse_and_revision_isolation(self):
        builder = CFGBuilder()
        file = FileInput(file_id='F', file_name='f.py', file_path='f.py',
                         file_content='def f():\n    while True:\n        break')
        original = builder.build(PythonParser().parse(file).tree.body[0], file, RevisionIds('P', 1))
        file.file_content = 'def f():\n    return 1'
        revised = builder.build(PythonParser().parse(file).tree.body[0], file, RevisionIds('P', 2))
        self.assertIn('break', [n.label for n in original.graph.nodes])
        self.assertNotIn('break', [n.label for n in revised.graph.nodes])
        self.assertTrue({n.node_id for n in original.graph.nodes}.isdisjoint(n.node_id for n in revised.graph.nodes))
        self.assertTrue(all(m.graph_id == revised.graph.graph_id for m in revised.source_mappings))

    def test_recursion_limit_returns_no_partial_graph(self):
        from unittest.mock import patch
        with patch('flowbridge_analysis.CFGBuilder._FunctionBuilder.block', side_effect=RecursionError):
            result = build('def f():\n    return 1')
        self.assertEqual(result.graph.status, 'failed')
        self.assertEqual(result.graph.nodes, [])
        self.assertEqual(result.source_mappings, [])
        self.assertEqual(result.diagnostics[0].code, 'CFG_LIMIT')

    def test_nested_definition_does_not_create_graph_and_bare_handler_must_be_last(self):
        for source in ['def f():\n    def inner():\n        return 1\n    return inner()',
                       'def f():\n    try:\n        work()\n    except:\n        pass\n    except ValueError:\n        pass']:
            self.assertEqual(build(source).graph.status, 'unsupported')
