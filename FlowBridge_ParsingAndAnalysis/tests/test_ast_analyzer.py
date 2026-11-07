"""Function metadata, lexical scope boundaries and unresolved call extraction."""
import json
from pathlib import Path
import unittest

from flowbridge_analysis import ASTAnalyzer, PythonParser, RevisionIds, validate_project
from flowbridge_analysis.models import FileInput


def analyze(source, file_id='F', path='module.py', revision=1):
    file = FileInput(file_id=file_id, file_name=path.split('/')[-1], file_path=path, file_content=source)
    parsed = PythonParser().parse(file)
    if parsed.tree is None:
        raise AssertionError(parsed.diagnostics)
    return ASTAnalyzer().analyze(parsed.tree, file, RevisionIds('P', revision))


class ASTAnalyzerTests(unittest.TestCase):
    def test_calculator_symbols_and_calls(self):
        payload = json.loads(Path('examples/calculator_input.json').read_text(encoding='utf-8-sig'))
        project = validate_project(payload).project
        file = project.files[0]
        result = ASTAnalyzer().analyze(PythonParser().parse(file).tree, file,
                                       RevisionIds(project.project_id, project.revision_id))
        self.assertEqual([f.qualified_name for f in result.functions], ['calculator.calculate', 'calculator.main'])
        table = result.symbol_table
        calculate, main = result.functions
        self.assertEqual([s.name for s in table.symbols if s.scope_id == result.module_scope_id], ['calculate', 'main'])
        self.assertEqual([s.name for s in table.symbols if s.scope_id == calculate.scope_id], ['a', 'b', 'result', 'result'])
        self.assertEqual([s.name for s in table.symbols if s.scope_id == main.scope_id], ['answer'])
        self.assertEqual([c.direct_name for c in result.call_sites], ['calculate', 'print'])
        self.assertEqual(result.diagnostics, [])
        self.assertEqual(len(table.bindings(calculate.scope_id, 'result')), 2)
        self.assertEqual(table.lookup(main.scope_id, 'calculate').bindings[0].function_id, calculate.function_id)

    def test_all_parameter_kinds_and_defaults(self):
        result = analyze('def f(a: int, b=1, /, c: str="s", *args: tuple, d, e=None, **kwargs: dict) -> bool:\n    return True')
        parameters = result.functions[0].parameters
        self.assertEqual([p.name for p in parameters], ['a', 'b', 'c', 'args', 'd', 'e', 'kwargs'])
        self.assertEqual([p.kind for p in parameters], ['positionalOnly', 'positionalOnly', 'positionalOrKeyword',
                                                     'varPositional', 'keywordOnly', 'keywordOnly', 'varKeyword'])
        self.assertEqual([p.has_default for p in parameters], [False, True, True, False, False, True, False])
        self.assertEqual([p.annotation for p in parameters], ['int', None, 'str', 'tuple', None, None, 'dict'])
        self.assertEqual(len(result.symbol_table.bindings(result.functions[0].scope_id, 'args')), 1)

    def test_no_parameters_and_empty_module(self):
        self.assertEqual(analyze('def f():\n    return').functions[0].parameters, [])
        empty = analyze('')
        self.assertEqual(empty.functions, [])
        self.assertEqual(len(empty.symbol_table.scopes), 1)

    def test_parameter_and_local_shadowing(self):
        result = analyze('def target():\n    return 1\ndef a(target):\n    return target()\n'
                         'def b():\n    target()\n    target = 2\n    return target')
        table = result.symbol_table
        self.assertEqual(table.lookup(result.functions[1].scope_id, 'target').bindings[0].kind, 'parameter')
        local = table.lookup(result.functions[2].scope_id, 'target')
        self.assertEqual(local.bindings[0].kind, 'local')
        self.assertIsNone(local.bindings[0].function_id)
        self.assertEqual(len(result.call_sites), 2)
        self.assertFalse(hasattr(result.call_sites[0], 'target_function_id'))

    def test_module_and_function_locals_are_distinct(self):
        result = analyze('x = 0\ndef f():\n    x = 1\n    y, *rest = values\n    obj.attr = x\n    items[0] = y\n    return x')
        table = result.symbol_table
        self.assertEqual(table.bindings(result.module_scope_id, 'x')[0].kind, 'module')
        scope = result.functions[0].scope_id
        self.assertEqual([s.name for s in table.symbols if s.scope_id == scope], ['x', 'y', 'rest'])
        self.assertFalse(any(d.code == 'UNSUPPORTED_FEATURE' for d in result.diagnostics))

    def test_duplicate_definitions_keep_distinct_ids(self):
        result = analyze('def f():\n    return 1\ndef f():\n    return 2')
        self.assertNotEqual(result.functions[0].function_id, result.functions[1].function_id)
        self.assertEqual(len(result.symbol_table.lookup(result.module_scope_id, 'f').bindings), 2)

    def test_multiple_files_and_revisions_are_isolated(self):
        source = 'def f():\n    return 1'
        first = analyze(source, 'F1', 'pkg/a.py')
        second = analyze(source, 'F2', 'pkg/b.py')
        self.assertEqual(first.functions[0].qualified_name, 'pkg.a.f')
        self.assertEqual(second.functions[0].qualified_name, 'pkg.b.f')
        self.assertNotEqual(first.functions[0].function_id, second.functions[0].function_id)
        self.assertEqual(first.to_dict(), analyze(source, 'F1', 'pkg/a.py').to_dict())
        self.assertNotEqual(first.functions[0].function_id, analyze(source, 'F1', 'pkg/a.py', 2).functions[0].function_id)
        self.assertNotIn(second.module_scope_id, [s.scope_id for s in first.symbol_table.scopes])

    def test_unicode_and_multiline_source_positions(self):
        source = 'def café(é):\n    résultat = call(\n        é\n    )\n    return résultat\n'
        result = analyze(source)
        function = result.functions[0]
        self.assertEqual((function.start_line, function.start_column, function.end_line, function.end_column),
                         (1, 0, 5, len('    return résultat'.encode('utf-8'))))
        parameter = result.symbol_table.bindings(function.scope_id, 'é')[0]
        self.assertEqual(parameter.location.start_column, len('def café('.encode('utf-8')))
        call = result.call_sites[0]
        self.assertEqual((call.location.start_line, call.location.start_column, call.location.end_line),
                         (2, len('    résultat = '.encode('utf-8')), 4))
        self.assertEqual(call.expression, 'call(\n        é\n    )')

    def test_nested_function_body_not_misattributed(self):
        result = analyze('def outer(x):\n    def inner(y=default()):\n        hidden = y\n        hidden_call()\n'
                         '        return y\n    return inner(x)')
        self.assertEqual([f.function_name for f in result.functions], ['outer'])
        scope = result.functions[0].scope_id
        self.assertEqual([s.name for s in result.symbol_table.symbols if s.scope_id == scope], ['x', 'inner'])
        self.assertEqual([c.direct_name for c in result.call_sites], ['inner'])
        self.assertFalse(result.symbol_table.scope(scope).is_complete)
        self.assertIsNone(result.symbol_table.bindings(scope, 'inner')[0].function_id)
        self.assertFalse(result.symbol_table.lookup(scope, 'missing').is_complete)

    def test_definition_defaults_and_decorators_have_module_scope(self):
        result = analyze('@decorate(factory())\ndef f(x=default(), *, y=kwdefault()):\n    return body(x)')
        module_calls = [c.direct_name for c in result.call_sites if c.caller_function_id is None]
        self.assertEqual(module_calls, ['decorate', 'factory', 'default', 'kwdefault'])
        self.assertEqual(result.call_sites[-1].caller_function_id, result.functions[0].function_id)
        self.assertFalse(result.symbol_table.scope(result.module_scope_id).is_complete)

    def test_annotations_not_reported_as_executed_calls(self):
        result = analyze('def f(x: annotation()) -> result_type():\n    return x')
        self.assertEqual(result.call_sites, [])
        self.assertEqual(result.functions[0].parameters[0].annotation, 'annotation()')

    def test_import_bindings_are_informational(self):
        result = analyze('import os.path\nimport pkg.mod as pm\nfrom pkg import helper as h\nfrom . import sibling\n')
        symbols = result.symbol_table.symbols
        self.assertEqual([(s.name, s.import_target) for s in symbols],
                         [('os', 'os'), ('pm', 'pkg.mod'), ('h', 'pkg.helper'), ('sibling', '.sibling')])
        self.assertTrue(all(s.kind == 'import' for s in symbols))
        self.assertTrue(result.diagnostics)
        self.assertFalse(analyze('from pkg import *').symbol_table.scopes[0].is_complete)

    def test_global_nonlocal_and_unsupported_scopes_stop_optimistic_lookup(self):
        result = analyze('x = 1\ndef f():\n    global x\n    x = 2\n    call()')
        scope = result.functions[0].scope_id
        self.assertEqual(result.symbol_table.bindings(scope, 'x'), [])
        self.assertEqual(result.call_sites, [])
        lookup = result.symbol_table.lookup(scope, 'x')
        self.assertFalse(lookup.is_complete)
        self.assertEqual(lookup.bindings, [])

    def test_inner_expression_scopes_stay_isolated_while_loops_are_walked(self):
        result = analyze('def f():\n    x = [hidden(i) for i in xs]\n    y = lambda z: other(z)\n'
                         '    for j in xs:\n        nested(j)\n    return visible()')
        scope = result.functions[0].scope_id
        self.assertEqual([s.name for s in result.symbol_table.symbols if s.scope_id == scope], ['x', 'y', 'j'])
        self.assertEqual([c.direct_name for c in result.call_sites], ['nested', 'visible'])
        self.assertFalse(result.symbol_table.scope(scope).is_complete)

    def test_attribute_and_chained_calls_are_separate(self):
        result = analyze('def f():\n    return obj.run(factory()())')
        self.assertEqual(len(result.call_sites), 3)
        self.assertEqual(len({c.call_id for c in result.call_sites}), 3)
        self.assertIn('obj.run', [c.callee_expression for c in result.call_sites])
        self.assertEqual(sum(c.direct_name is not None for c in result.call_sites), 1)

    def test_analyzer_reuse_and_debug_json(self):
        analyzer = ASTAnalyzer()
        file = FileInput(file_id='F', file_name='f.py', file_path='f.py', file_content='def f():\n    return 1')
        tree = PythonParser().parse(file).tree
        first = analyzer.analyze(tree, file, RevisionIds('P', 1))
        second = analyzer.analyze(tree, file, RevisionIds('P', 1))
        first.symbol_table.mark_incomplete(first.module_scope_id)
        self.assertTrue(second.symbol_table.scope(second.module_scope_id).is_complete)
        self.assertEqual(json.loads(json.dumps(second.to_dict()))['functions'][0]['functionName'], 'f')
        self.assertNotIn('graphs', second.to_dict())
