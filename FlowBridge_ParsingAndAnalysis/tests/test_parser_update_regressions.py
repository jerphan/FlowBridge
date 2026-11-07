"""Integration regressions found while reviewing the procedural-CFG update."""

import unittest
from unittest.mock import patch

from flowbridge_analysis import CFGBuilder, FlowchartOutput, MappingOutput, ParsingAnalysisService


def project(*sources):
    return {
        "projectId": "review",
        "projectName": "Review",
        "revisionId": 3,
        "files": [
            {"fileId": name, "fileName": name, "filePath": name, "fileContent": source}
            for name, source in sources
        ],
    }


class ParserUpdateRegressions(unittest.TestCase):
    def test_returns_in_module_containers_are_unsupported(self):
        sources = [
            "if True:\n    return 1\n",
            "for x in [1]:\n    return x\n",
            "try:\n    return 1\nexcept Exception:\n    pass\n",
        ]
        for source in sources:
            with self.subTest(source=source):
                result = ParsingAnalysisService().analyze_project(project(("main.py", source)))
                self.assertEqual(result.status, "partial")
                self.assertTrue(
                    any(
                        "return statement outside function" in d.message for d in result.diagnostics
                    )
                )
                module = next(g for g in result.graphs.values() if g.graph_type == "module")
                self.assertEqual(module.status, "unsupported")
                self.assertEqual(module.nodes, [])

    def test_omitted_try_bindings_do_not_resolve_to_a_wrong_global_function(self):
        bodies = [
            "    try:\n        pass\n    finally:\n        target = 2\n    return target()\n",
            "    try:\n        x = 1\n    except Exception:\n        pass\n"
            "    else:\n        target = 2\n    return target()\n",
            "    try:\n        x = 1\n    except Exception as target:\n        target()\n",
        ]
        for body in bodies:
            with self.subTest(body=body):
                source = "def target():\n    return 1\ndef run():\n" + body
                result = ParsingAnalysisService().analyze_project(project(("main.py", source)))
                self.assertEqual(result.status, "partial")
                self.assertTrue(any(d.code == "INCOMPLETE_SCOPE" for d in result.diagnostics))
                call = next(c for c in result.call_references if c.expression == "target()")
                self.assertEqual(call.resolution, "unresolved")
                self.assertEqual(call.reason, "Incomplete lexical scope")

    def test_failed_cfg_construction_retains_valid_siblings_without_partial_file_state(self):
        good = ("good.py", "def good():\n    return 1\nvalue = good()\n")
        bad = (
            "broken.py",
            "def first():\n    return 1\ndef broken():\n    return 2\nx = first()\n",
        )
        for method in ("build", "build_module"):
            original = getattr(CFGBuilder, method)

            def fail_one_file(
                builder, tree, file_input, ids, failure_stage=method, original_build=original
            ):
                if file_input.file_name == "broken.py" and (
                    failure_stage == "build_module" or tree.name == "broken"
                ):
                    raise RuntimeError("simulated CFG construction failure")
                return original_build(builder, tree, file_input, ids)

            for sources in ((good, bad), (bad, good)):
                with self.subTest(method=method, first_file=sources[0][0]):
                    with patch.object(CFGBuilder, method, fail_one_file):
                        result = ParsingAnalysisService().analyze_project(project(*sources))
                    self.assertEqual(result.status, "partial")
                    self.assertEqual(
                        {f.file_id: f.status for f in result.files},
                        {"good.py": "complete", "broken.py": "failed"},
                    )
                    self.assertEqual([f.function_name for f in result.functions], ["good"])
                    failed = next(g for g in result.graphs.values() if g.file_id == "broken.py")
                    self.assertEqual(failed.graph_type, "file")
                    self.assertEqual(failed.nodes, [])
                    self.assertTrue(
                        any(d.code == "INTERNAL_ANALYSIS_ERROR" for d in result.diagnostics)
                    )
                    self.assertTrue(
                        all(m.location.file_id == "good.py" for m in result.source_mappings)
                    )
                    self.assertTrue(all(c.file_id == "good.py" for c in result.call_references))
                    self.assertEqual(FlowchartOutput(result).to_dict()["status"], "partial")
                    self.assertEqual(MappingOutput(result).to_dict()["status"], "partial")
