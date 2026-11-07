"""Requested parsing/metadata phases: behavior without CFG construction."""
import ast
import unittest
from unittest.mock import patch

from flowbridge_analysis import ASTAnalyzer, FeatureValidator, InputValidator, PythonParser, RevisionIds
from flowbridge_analysis.models import FileInput

CALCULATOR = ('def calculate(a, b):\n    result = a + b\n    return result\n\n'
              'def main():\n    answer = calculate(10, 5)\n    print(answer)\n')


def inspect(source: str, file_id: str = 'F', path: str = 'calculator.py'):
    """Parse source as data and return metadata for its exact snapshot."""
    file = FileInput(file_id=file_id, file_name=path, file_path=path, file_content=source)
    parsed = PythonParser().parse(file)
    if parsed.tree is None:
        raise AssertionError(parsed.diagnostics)
    return ASTAnalyzer().analyze(parsed.tree, file, RevisionIds('P', 1))


class PhaseThreeTests(unittest.TestCase):
    def test_parse_identity_on_success_empty_syntax_and_encoding_failures(self) -> None:
        for source in (CALCULATOR, '', 'def broken(:', '\ud800'):
            with self.subTest(source=source):
                file = FileInput(file_id=' exact:F ', file_name='f.py', file_path='f.py', file_content=source)
                result = PythonParser().parse(file)
                self.assertEqual(result.file_id, file.file_id)
                self.assertTrue(all(item.file_id == file.file_id for item in result.diagnostics))

    def test_parser_receives_supplied_path_without_opening_it(self) -> None:
        file = FileInput(file_id='F', file_name='f.py', file_path='not/on/disk.py', file_content='')
        with patch('flowbridge_analysis.PythonParser.ast.parse', wraps=ast.parse) as parse:
            result = PythonParser().parse(file)
        self.assertTrue(result.syntax_valid)
        parse.assert_called_once_with('', filename='not/on/disk.py', mode='exec')

    def test_nested_conditions_and_loop_context(self) -> None:
        source = ('def f(xs):\n    for x in xs:\n        while x:\n            if x > 2:\n'
                  '                break\n            elif x:\n                continue\n'
                  '            else:\n                return x\n    return 0')
        tree = ast.parse(source)
        before = ast.dump(tree, include_attributes=True)
        self.assertTrue(FeatureValidator().validate(tree, 'F').is_supported)
        self.assertEqual(ast.dump(tree, include_attributes=True), before)
        outside = ast.parse('def f(xs):\n    for x in xs:\n        pass\n    break')
        result = FeatureValidator().validate(outside, 'F')
        self.assertFalse(result.is_supported)
        self.assertEqual(result.diagnostics[0].source_location.start_line, 4)

    def test_try_subset_remains_explicitly_conservative(self) -> None:
        tree = ast.parse('def f():\n    try:\n        work()\n    except ValueError:\n        recover()')
        result = FeatureValidator().validate(tree, 'F')
        self.assertTrue(result.is_supported)
        self.assertEqual([item.code for item in result.diagnostics], ['CONSERVATIVE_EXCEPTIONS'])
        unsupported = ast.parse('class C:\n    pass')
        result = FeatureValidator().validate(unsupported, 'class-file')
        self.assertFalse(result.is_supported)
        self.assertEqual(result.diagnostics[0].code, 'UNSUPPORTED_FEATURE')
        self.assertEqual(result.diagnostics[0].file_id, 'class-file')

    def test_multifile_project_keeps_invalid_file_isolated(self) -> None:
        sources = [CALCULATOR, 'def broken(:', '', 'class C:\n    pass']
        payload = dict(projectId='P', projectName='Demo', revisionId=1, files=[])
        for index, source in enumerate(sources):
            payload['files'].append(dict(fileId=str(index), fileName=f'f{index}.py',
                                         filePath=f'f{index}.py', fileContent=source))
        project = InputValidator().validate(payload).project
        parsed = [PythonParser().parse(file) for file in project.files]
        self.assertEqual([result.file_id for result in parsed], ['0', '1', '2', '3'])
        self.assertEqual([result.syntax_valid for result in parsed], [True, False, True, True])
        self.assertEqual(parsed[1].diagnostics[0].code, 'SYNTAX_ERROR')
        metadata = {}
        for file, result in zip(project.files, parsed):
            if result.tree is not None:
                metadata[file.file_id] = ASTAnalyzer().analyze(result.tree, file, RevisionIds('P', 1))
        self.assertEqual([item.function_name for item in metadata['0'].functions], ['calculate', 'main'])
        self.assertEqual(metadata['2'].functions, [])
        self.assertEqual(metadata['3'].diagnostics[0].code, 'UNSUPPORTED_FEATURE')
        self.assertNotIn('1', metadata)


class PhaseFourTests(unittest.TestCase):
    def test_exact_calculator_metadata_symbols_and_lookup(self) -> None:
        result = inspect(CALCULATOR)
        calculate, main = result.functions
        self.assertEqual([item.qualified_name for item in result.functions],
                         ['calculator.calculate', 'calculator.main'])
        self.assertEqual([parameter.name for parameter in calculate.parameters], ['a', 'b'])
        self.assertEqual(main.parameters, [])
        self.assertEqual((calculate.start_line, calculate.end_line, calculate.start_column, calculate.end_column),
                         (1, 3, 0, 17))
        self.assertEqual((main.start_line, main.end_line, main.start_column, main.end_column), (5, 7, 0, 17))
        symbols = [symbol for symbol in result.symbol_table.symbols if symbol.scope_id == calculate.scope_id]
        self.assertEqual([(symbol.name, symbol.kind) for symbol in symbols],
                         [('a', 'parameter'), ('b', 'parameter'), ('result', 'local')])
        self.assertEqual(result.symbol_table.lookup(calculate.scope_id, 'result').bindings[0].location.start_line, 2)
        declaration = result.symbol_table.lookup(main.scope_id, 'calculate').bindings[0]
        self.assertEqual(declaration.function_id, calculate.function_id)
        self.assertEqual([call.direct_name for call in result.call_sites], ['calculate', 'print'])
        self.assertEqual(result.diagnostics, [])
        self.assertNotIn('graphs', result.to_dict())

    def test_loop_bindings_calls_and_shadowing(self) -> None:
        result = inspect('x = 0\ndef f(xs):\n    for x, y in source(xs):\n        z = use(x)\n'
                         '        while check(y):\n            y = step(y)\n            break\n'
                         '        continue\n    return z')
        scope = result.functions[0].scope_id
        names = [symbol.name for symbol in result.symbol_table.symbols if symbol.scope_id == scope]
        self.assertEqual(names, ['xs', 'x', 'y', 'z', 'y'])
        self.assertEqual([call.direct_name for call in result.call_sites], ['source', 'use', 'check', 'step'])
        self.assertTrue(result.symbol_table.scope(scope).is_complete)
        self.assertEqual(result.symbol_table.lookup(scope, 'x').scope_id, scope)
        self.assertTrue(all(call.caller_function_id == result.functions[0].function_id for call in result.call_sites))

    def test_zero_iteration_loop_still_introduces_lexical_binding(self) -> None:
        result = inspect('x = 0\ndef f():\n    while False:\n        x = work()\n    return x')
        scope = result.functions[0].scope_id
        self.assertEqual(result.symbol_table.lookup(scope, 'x').scope_id, scope)
        self.assertEqual([call.direct_name for call in result.call_sites], ['work'])

    def test_nested_function_in_loop_does_not_leak_inner_bindings(self) -> None:
        result = inspect('def outer(xs):\n    for x in xs:\n        def inner(y):\n'
                         '            hidden = secret(y)\n        use(x)')
        scope = result.functions[0].scope_id
        self.assertEqual([item.function_name for item in result.functions], ['outer'])
        self.assertEqual([item.name for item in result.symbol_table.symbols if item.scope_id == scope],
                         ['xs', 'x', 'inner'])
        self.assertEqual([call.direct_name for call in result.call_sites], ['use'])
        self.assertFalse(result.symbol_table.scope(scope).is_complete)

    def test_loop_else_and_try_are_complete(self) -> None:
        for body in ('for x in xs:\n        work()\n    else:\n        finish()',
                     'try:\n        work()\n    except:\n        recover()'):
            result = inspect('def f(xs):\n    ' + body)
            self.assertTrue(result.symbol_table.scope(result.functions[0].scope_id).is_complete)
            self.assertFalse(any(item.code == 'INCOMPLETE_SCOPE' for item in result.diagnostics))

    def test_identical_names_are_separate_across_scopes_and_files(self) -> None:
        source = 'def f(x):\n    result = x\n    return result\ndef g(x):\n    result = x\n    return result'
        first = inspect(source, 'A', 'a.py')
        second = inspect(source, 'B', 'b.py')
        identifiers = [function.function_id for result in (first, second) for function in result.functions]
        self.assertEqual(len(set(identifiers)), 4)
        for result in (first, second):
            for function in result.functions:
                binding = result.symbol_table.lookup(function.scope_id, 'result')
                self.assertEqual(binding.scope_id, function.scope_id)
                self.assertEqual(binding.bindings[0].file_id, result.file_id)

    def test_mutated_scope_cycle_fails_instead_of_hanging(self) -> None:
        result = inspect(CALCULATOR)
        function_scope = result.functions[0].scope_id
        result.symbol_table.scope(result.module_scope_id).parent_scope_id = function_scope
        with self.assertRaisesRegex(ValueError, 'Cycle'):
            result.symbol_table.lookup(function_scope, 'missing')
