"""Scope/import resolution behavior, without executing fixture source."""
import unittest
from flowbridge_analysis import ASTAnalyzer, PythonParser, RevisionIds, CallResolver
from flowbridge_analysis.models import FileInput


def resolve(sources, revision=1):
    files = []
    analyses = []
    for index, (path, source) in enumerate(sources):
        file = FileInput(file_id=str(index), file_name=path.split('/')[-1], file_path=path, file_content=source)
        files.append(file)
        parsed = PythonParser().parse(file)
        if parsed.tree is not None:
            analyses.append(ASTAnalyzer().analyze(parsed.tree, file, RevisionIds('P', revision)))
    return CallResolver().resolve(files, analyses), analyses


class CallResolverTests(unittest.TestCase):
    def test_same_file_forward_recursion_and_builtin(self):
        result, analyses = resolve([('main.py', 'def main():\n    print(calculate())\ndef calculate():\n    return calculate()')])
        self.assertEqual([c.resolution for c in result.call_references], ['builtin', 'resolved', 'resolved'])
        target = analyses[0].functions[1]
        for call in result.call_references[1:]:
            self.assertEqual(call.target_function_id, target.function_id)
            self.assertEqual(call.target_graph_id, target.graph_id)
            self.assertEqual(call.location.file_id, '0')

    def test_cross_file_import_variants(self):
        for statement, expression in [('from calculator import add', 'add'),
                                      ('from calculator import add as plus', 'plus'),
                                      ('import calculator', 'calculator.add'),
                                      ('import calculator as c', 'c.add')]:
            with self.subTest(statement=statement):
                result, analyses = resolve([('calculator.py', 'def add(a,b):\n    return a+b'),
                    ('main.py', statement + '\ndef main():\n    return ' + expression + '(10,5)')])
                call = result.call_references[0]
                self.assertEqual(call.resolution, 'resolved')
                self.assertEqual(call.target_function_id, analyses[0].functions[0].function_id)
                self.assertEqual(len(result.import_relationships), 1)
                self.assertEqual(call.location.start_line, 3)

    def test_dotted_module(self):
        result, _ = resolve([('pkg/calc.py', 'def add():\n    pass'),
                            ('main.py', 'import pkg.calc\ndef main():\n    pkg.calc.add()')])
        self.assertEqual(result.call_references[0].resolution, 'resolved')

    def test_no_project_wide_guess(self):
        result, _ = resolve([('other.py', 'def add():\n    pass'), ('main.py', 'def main():\n    add()')])
        self.assertEqual(result.call_references[0].resolution, 'unresolved')

    def test_shadowed_names(self):
        for body in ['def main(add):\n    add()', 'def main():\n    add()\n    add = 3']:
            result, _ = resolve([('main.py', 'def add():\n    pass\n' + body)])
            self.assertEqual(result.call_references[0].resolution, 'unresolved')

    def test_duplicate_declarations(self):
        result, _ = resolve([('main.py', 'def f():\n    pass\ndef f():\n    pass\ndef main():\n    f()')])
        self.assertEqual(result.call_references[0].resolution, 'ambiguous')

    def test_duplicate_modules(self):
        result, _ = resolve([('calc.py', 'def add():\n    pass'), ('calc/__init__.py', 'def add():\n    pass'),
                            ('main.py', 'from calc import add\ndef main():\n    add()')])
        self.assertEqual(result.call_references[0].resolution, 'ambiguous')

    def test_external_and_failed_module(self):
        result, _ = resolve([('main.py', 'from missing import f\ndef main():\n    f()')])
        self.assertEqual(result.call_references[0].resolution, 'external')
        result, _ = resolve([('missing.py', 'def !'), ('main.py', 'from missing import f\ndef main():\n    f()')])
        self.assertEqual(result.call_references[0].resolution, 'unresolved')

    def test_dynamic_relative_and_conditional_imports(self):
        sources = ['def main(xs):\n    xs[0]()', 'from .calc import f\ndef main():\n    f()',
                   'if flag:\n    from calc import f\ndef main():\n    f()',
                   'def main():\n    from calc import f\n    f()']
        for source in sources:
            with self.subTest(source=source):
                result, _ = resolve([('main.py', source)])
                self.assertEqual(result.call_references[0].resolution, 'unresolved')

    def test_incomplete_scope_blocks_optimistic_resolution(self):
        result, _ = resolve([('main.py', 'def f():\n    pass\ndef main():\n    _ = [x for x in []]\n    f()')])
        self.assertEqual(result.call_references[0].resolution, 'unresolved')

    def test_determinism_and_revision_isolation(self):
        sources = [('main.py', 'def f():\n    f()')]
        a, _ = resolve(sources)
        b, _ = resolve(sources)
        c, _ = resolve(sources, 2)
        self.assertEqual(a.call_references[0].to_dict(), b.call_references[0].to_dict())
        self.assertNotEqual(a.call_references[0].target_function_id, c.call_references[0].target_function_id)
