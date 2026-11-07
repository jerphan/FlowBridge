"""Feature allowlist tests separate from parsing and graph construction."""
import ast
import unittest
from flowbridge_analysis import FeatureValidator, PythonParser
from flowbridge_analysis.models import FileInput


def inspect_source(source):
    file = FileInput(file_id='F', file_name='f.py', file_path='f.py', file_content=source)
    parsed = PythonParser().parse(file)
    if parsed.tree is None:
        raise AssertionError(parsed.diagnostics)
    return FeatureValidator().validate(parsed.tree, file.file_id)


class FeatureValidatorTests(unittest.TestCase):
    def test_initial_statements_and_nested_branches(self):
        source = ('def f(x):\n    y = x + 1\n    print(y)\n'
                  '    if x:\n        if y > 1:\n            return y\n'
                  '        else:\n            return 0\n    elif y:\n        y = 2\n'
                  '    else:\n        y = 3\n    return y\n')
        self.assertTrue(inspect_source(source).is_supported)

    def test_signatures_defaults_annotations_and_atomic_expressions(self):
        source = ('def f(a: int, /, b=1, *args, c=None, **kwargs) -> str:\n'
                  '    "doc"\n    x, *rest = [a, b]\n'
                  '    y = {"x": (a + b) if a and b else -1}\n'
                  '    return f"{obj.value(y[\"x\"], *args, **kwargs):.2f}"\n')
        self.assertTrue(inspect_source(source).is_supported)

    def test_docstring_empty_and_multiple_functions(self):
        for source in ['', '# comment', '"module docs"\ndef a():\n    return\ndef b():\n    return 1']:
            self.assertTrue(inspect_source(source).is_supported)

    def test_nested_function_is_unsupported(self):
        result = inspect_source('def outer():\n    def inner():\n        return 1\n    return inner()')
        self.assertFalse(result.is_supported)
        self.assertIn('function outer', result.diagnostics[0].message)
        self.assertIn('FunctionDef', result.diagnostics[0].message)
        self.assertEqual(result.diagnostics[0].source_location.start_line, 2)

    def test_unsupported_exception_forms(self):
        statements = ['try:\n        x = 1\n    except Exception as error:\n        return 0',
                      'try:\n        x = 1\n    finally:\n        x = 2']
        for statement in statements:
            with self.subTest(statement=statement):
                result = inspect_source('def f():\n    ' + statement + '\n')
                self.assertFalse(result.is_supported)
                self.assertIn('UNSUPPORTED_FEATURE', [item.code for item in result.diagnostics])

    def test_other_unsupported_statements(self):
        for statement in ['raise ValueError()',
                          'import os', 'global x', 'assert x', 'del x',
                          'with open("x") as f:\n        return f',
                          'match x:\n        case 1:\n            return 1']:
            with self.subTest(statement=statement):
                self.assertFalse(inspect_source('def f():\n    ' + statement).is_supported)

    def test_unsupported_expressions_cannot_hide(self):
        for expression in ['[x for x in xs]', '{x for x in xs}', '{x:x for x in xs}',
                           '(x for x in xs)', 'lambda x: x', '(yield 1)', '(yield from xs)',
                           'await task()', '(x := 1)', 'call([x for x in xs])']:
            with self.subTest(expression=expression):
                result = inspect_source('def f():\n    return ' + expression)
                self.assertFalse(result.is_supported)

    def test_signature_expressions_are_inspected(self):
        for source in ['def f(x=[i for i in xs]):\n    return x',
                       'def f(x: (lambda: 1)):\n    return x']:
            self.assertFalse(inspect_source(source).is_supported)

    def test_async_class_decorator_and_type_parameters(self):
        for source in ['async def f():\n    return 1', 'class C:\n    x = 1',
                       '@decorate\ndef f():\n    return 1', 'def f[T](x: T):\n    return x']:
            with self.subTest(source=source):
                self.assertFalse(inspect_source(source).is_supported)

    def test_module_execution_is_supported(self):
        for source in ['x = 1', 'print(1)', 'if True:\n    x = 1',
                       '"doc"\n"another string"']:
            result = inspect_source(source)
            self.assertTrue(result.is_supported)

    def test_module_unsupported_statements(self):
        for source in ['return 1', 'class C:\n    pass']:
            result = inspect_source(source)
            self.assertFalse(result.is_supported)
            self.assertIn('<module>', result.diagnostics[0].message)

    def test_checks_unreachable_and_other_functions(self):
        source = ('def f():\n    return 1\n    with resource():\n        return 2\n'
                  'def g():\n    x = [i for i in xs]\n    return x')
        result = inspect_source(source)
        self.assertEqual(len(result.diagnostics), 2)
        self.assertIn('function f', result.diagnostics[0].message)
        self.assertIn('function g', result.diagnostics[1].message)

    def test_ast_byte_locations_and_json_diagnostics(self):
        result = inspect_source('def f():\n    é = [x for x in xs]')
        location = result.diagnostics[0].source_location
        self.assertEqual(location.start_column, len('    é = '.encode('utf-8')))
        self.assertEqual(result.diagnostics[0].to_dict()['fileId'], 'F')
        self.assertIsNone(result.diagnostics[0].graph_id)

    def test_validator_is_stateless_and_does_not_modify_ast(self):
        tree = ast.parse('def f():\n    with resource():\n        return 1')
        before = ast.dump(tree, include_attributes=True)
        validator = FeatureValidator()
        first = validator.validate(tree, 'F')
        second = validator.validate(ast.parse('def f():\n    return 1'), 'G')
        self.assertFalse(first.is_supported)
        self.assertTrue(second.is_supported)
        self.assertEqual(ast.dump(tree, include_attributes=True), before)
        self.assertEqual(first.diagnostics, validator.validate(tree, 'F').diagnostics)

    def test_invalid_api_use_and_unknown_ast_fail_closed(self):
        with self.assertRaises(TypeError):
            FeatureValidator().validate(None, 'F')
        class FutureExpression(ast.expr):
            _fields = ()
        tree = ast.parse('def f():\n    return 1')
        tree.body[0].body[0].value = FutureExpression()
        self.assertFalse(FeatureValidator().validate(tree, 'F').is_supported)
