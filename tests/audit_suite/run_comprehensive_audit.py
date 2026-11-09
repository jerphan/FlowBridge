"""Comprehensive Parsing & Analysis Audit Execution Script for FlowBridge.

Executes real tests against FlowBridge Parsing & Analysis module and captures
exact outputs, diagnostics, node types, edges, and call resolutions.
"""

import json
import os
from pathlib import Path

from flowbridge_analysis import (
    ParsingAnalysisService,
)
from flowbridge_analysis.models import (
    FileInput,
    ProjectAnalysis,
    ProjectInput,
)

_root = Path(__file__).resolve().parents[2]


def run_pipeline(files: list[FileInput], project_id: str = "audit_proj") -> ProjectAnalysis:
    service = ParsingAnalysisService()
    payload = ProjectInput(
        project_id=project_id,
        project_name="Audit Project",
        revision_id=1,
        files=files,
    ).to_dict()
    return service.analyze_project(payload)


def run_single(name: str, code: str, path: str | None = None) -> ProjectAnalysis:
    f = FileInput(
        file_id="f_single",
        file_name=name,
        file_path=path or name,
        file_content=code,
    )
    return run_pipeline([f], project_id="audit_single")


def test_project_full(stress_dir: Path) -> dict:
    files = []
    for root, _, filenames in os.walk(stress_dir):
        for fname in sorted(filenames):
            if fname.endswith(".py"):
                full_p = Path(root) / fname
                rel_p = str(full_p.relative_to(stress_dir)).replace("\\", "/")
                content = full_p.read_text(encoding="utf-8")
                files.append(FileInput(
                    file_id=f"file_{len(files)}",
                    file_name=fname,
                    file_path=rel_p,
                    file_content=content,
                ))

    res = run_pipeline(files, project_id="full_stress_proj")
    return {
        "status": res.status,
        "files_count": len(res.files),
        "file_statuses": {f.file_name: (f.status, f.file_path) for f in res.files},
        "diagnostics": [
            {
                "severity": d.severity,
                "code": d.code,
                "file_id": d.file_id,
                "message": d.message,
                "line": d.source_location.start_line if d.source_location else None,
            }
            for d in res.diagnostics
        ],
        "graphs": {
            gid: {
                "type": g.graph_type,
                "status": g.status,
                "nodes": len(g.nodes),
                "edges": len(g.edges),
            }
            for gid, g in res.graphs.items()
        },
        "calls": [
            {
                "expr": c.expression,
                "resolution": c.resolution,
                "reason": c.reason,
                "file_id": c.file_id,
                "target_fn": c.target_function_id,
            }
            for c in res.call_references
        ],
    }


def main():
    stress_dir = _root / "tests" / "temp_complex_project" / "FlowBridge_Stress_Project"
    out_dir = _root / "tests" / "audit_suite"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Running Full Stress Project Analysis...")
    full_results = test_project_full(stress_dir)

    print(f"Full Project Status: {full_results['status']}")
    print(f"Total Diagnostics: {len(full_results['diagnostics'])}")

    # Detailed test inventory of 15 stress project files individually
    manifest_path = stress_dir / "TEST_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    stress_files_results = {}
    for rel_path in manifest["python_files"]:
        p = stress_dir / rel_path
        code = p.read_text(encoding="utf-8")
        res = run_single(p.name, code, path=rel_path)
        stress_files_results[rel_path] = {
            "status": res.files[0].status,
            "diagnostics": [
                {
                    "severity": d.severity,
                    "code": d.code,
                    "message": d.message,
                    "line": d.source_location.start_line if d.source_location else None,
                }
                for d in res.diagnostics
            ],
            "graphs": [
                {
                    "type": g.graph_type,
                    "status": g.status,
                    "nodes": len(g.nodes),
                    "edges": len(g.edges),
                }
                for g in res.graphs.values()
            ],
            "calls": [
                {
                    "expr": c.expression,
                    "resolution": c.resolution,
                    "reason": c.reason,
                }
                for c in res.call_references
            ],
        }

    # Dedicated Category Tests (A - I)
    category_tests = {}

    # Category A: Basic Control Flow
    print("Testing Category A: Basic Control Flow...")
    cat_a_code = """
def test_control_flow(x):
    a = 1
    b = 2
    if x > 0:
        c = a + b
    elif x == 0:
        c = 0
    else:
        c = -1
    total = 0
    for i in [1, 2, 3]:
        if i == 2:
            continue
        total += i
    while total > 0:
        total -= 1
        if total == 1:
            break
    if x < -10:
        return -999
    return total
"""
    res_a = run_single("control_flow.py", cat_a_code)
    fn_a = res_a.functions[0]
    g_a = res_a.graphs[fn_a.graph_id]
    category_tests["A_basic_control_flow"] = {
        "status": res_a.status,
        "diagnostics": [d.message for d in res_a.diagnostics],
        "nodes": [(n.node_id, n.node_type, n.label) for n in g_a.nodes],
        "edges": [(e.source_id, e.target_id, e.edge_type) for e in g_a.edges],
    }

    # Category B: Exception Handling
    print("Testing Category B: Exception Handling Matrix...")
    b_cases = {
        "try_except_simple": "def f():\n    try:\n        x = 1 // 0\n    except ZeroDivisionError:\n        x = 0\n    return x",
        "try_except_module": "try:\n    x = 1 // 0\nexcept ZeroDivisionError:\n    x = 0",
        "try_multiple_except": "def f(x):\n    try:\n        y = 10 // x\n    except ZeroDivisionError:\n        y = 0\n    except ValueError:\n        y = -1\n    return y",
        "try_nested": "def f():\n    try:\n        try:\n            x = 1\n        except Exception:\n            x = 2\n    except Exception:\n        x = 3",
        "try_except_else": "def f():\n    try:\n        x = 1\n    except Exception:\n        x = 2\n    else:\n        x = 3",
        "try_finally": "def f():\n    try:\n        x = 1\n    finally:\n        x = 2",
        "try_except_else_finally": "def f():\n    try:\n        x = 1\n    except Exception:\n        x = 2\n    else:\n        x = 3\n    finally:\n        x = 4",
        "raise_statement": "def f():\n    raise ValueError('error')",
        "raise_reraise": "def f():\n    try:\n        x = 1\n    except Exception:\n        raise",
        "return_inside_try": "def f():\n    try:\n        return 1\n    except Exception:\n        return 2",
        "return_inside_finally": "def f():\n    try:\n        return 1\n    finally:\n        return 2",
        "break_inside_try": "def f():\n    for i in [1, 2]:\n        try:\n            break\n        except Exception:\n            pass",
        "except_alias": "def f():\n    try:\n        x = 1\n    except Exception as e:\n        x = 2",
    }
    cat_b_results = {}
    for name, code in b_cases.items():
        res_b = run_single(f"{name}.py", code)
        cat_b_results[name] = {
            "file_status": res_b.files[0].status,
            "diagnostics": [(d.severity, d.code, d.message) for d in res_b.diagnostics],
            "graph_statuses": {g.graph_type: (g.status, len(g.nodes), len(g.edges)) for g in res_b.graphs.values()},
        }
    category_tests["B_exception_handling"] = cat_b_results

    # Category C: Module-Level Execution
    print("Testing Category C: Module-Level Execution...")
    c1 = "x = 10\ny = 20\nprint(x + y)\n"
    res_c1 = run_single("c1_no_func.py", c1)
    g_c1 = next(g for g in res_c1.graphs.values() if g.graph_type == "file")

    c2 = "def foo():\n    return 42\nx = foo()\n"
    res_c2 = run_single("c2_func_and_call.py", c2)
    g_c2 = next(g for g in res_c2.graphs.values() if g.graph_type == "file")

    c3 = "def a(): pass\ndef b(): pass\n"
    res_c3 = run_single("c3_only_defs.py", c3)
    g_c3 = next(g for g in res_c3.graphs.values() if g.graph_type == "file")

    category_tests["C_module_level_execution"] = {
        "no_funcs_nodes": [(n.node_type, n.label) for n in g_c1.nodes],
        "no_funcs_edges": [(e.source_id, e.target_id, e.edge_type) for e in g_c1.edges],
        "func_and_call_nodes": [(n.node_type, n.label) for n in g_c2.nodes],
        "only_defs_nodes": [(n.node_type, n.label) for n in g_c3.nodes],
        "only_defs_edges": [(e.source_id, e.target_id, e.edge_type) for e in g_c3.edges],
    }

    # Category D: Same-File Function Calls
    print("Testing Category D: Same-File Function Calls...")
    d_code = """def add(a, b):
    return a + b

def main():
    result = add(5, 4)
    print(result)

main()
"""
    res_d = run_single("same_file_calls.py", d_code)
    fn_main_d = next(f for f in res_d.functions if f.function_name == "main")
    g_main_d = res_d.graphs[fn_main_d.graph_id]
    g_file_d = next(g for g in res_d.graphs.values() if g.graph_type == "file")

    category_tests["D_same_file_calls"] = {
        "function_view_main_nodes": [(n.node_type, n.label) for n in g_main_d.nodes],
        "file_view_nodes": [(n.node_type, n.label) for n in g_file_d.nodes],
        "file_view_edges": [(e.source_id, e.target_id, e.edge_type) for e in g_file_d.edges],
        "call_references": [(c.expression, c.resolution, c.target_function_id) for c in res_d.call_references],
        "graph_references": [(gr.source_graph_id, gr.source_node_id, gr.target_graph_id) for gr in res_d.graph_references],
    }

    # Category E: Imported Function Calls
    print("Testing Category E: Imported Function Calls...")
    f_calc = FileInput(file_id="f_calc", file_name="calculator.py", file_path="calculator.py",
                       file_content="def add(a, b):\n    return a + b\n")
    f_main = FileInput(file_id="f_main", file_name="main.py", file_path="main.py",
                       file_content="from calculator import add\nresult = add(5, 4)\nprint(result)\n")
    f_mod = FileInput(file_id="f_mod", file_name="caller_mod.py", file_path="caller_mod.py",
                      file_content="import calculator\nresult = calculator.add(5, 4)\n")
    f_alias = FileInput(file_id="f_alias", file_name="caller_alias.py", file_path="caller_alias.py",
                        file_content="import calculator as calc\nresult = calc.add(5, 4)\n")
    f_rel = FileInput(file_id="f_rel", file_name="sub/caller_rel.py", file_path="sub/caller_rel.py",
                      file_content="from ..calculator import add\nresult = add(5, 4)\n")

    res_e = run_pipeline([f_calc, f_main, f_mod, f_alias, f_rel], project_id="e_import_proj")
    category_tests["E_imported_calls"] = {
        "project_edges": [(e.source_id, e.target_id, e.label) for e in next(g for g in res_e.graphs.values() if g.graph_type == "project").edges],
        "calls": [(c.file_id, c.expression, c.resolution, c.reason, c.target_function_id) for c in res_e.call_references],
        "graph_references": [(gr.source_graph_id, gr.target_graph_id) for gr in res_e.graph_references],
    }

    # Category F: Nested and Embedded Function Calls
    print("Testing Category F: Nested Calls...")
    f_code = """def add(x, y): return x + y
def subtract(x, y): return x - y
def multiply(x, y): return x * y

def test_nested():
    res = multiply(add(2, 3), subtract(10, 4))
    return res

test_nested()
"""
    res_f = run_single("nested_calls.py", f_code)
    fn_f = next(f for f in res_f.functions if f.function_name == "test_nested")
    g_fn_f = res_f.graphs[fn_f.graph_id]
    g_file_f = next(g for g in res_f.graphs.values() if g.graph_type == "file")

    category_tests["F_nested_calls"] = {
        "calls_discovered": [(c.expression, c.resolution) for c in res_f.call_references],
        "fn_view_nodes": [(n.node_type, n.label) for n in g_fn_f.nodes],
        "file_view_nodes": [(n.node_type, n.label) for n in g_file_f.nodes],
    }

    # Category G: Recursion
    print("Testing Category G: Recursion...")
    g_code = """def rec(n):
    if n <= 0:
        return 0
    return n + rec(n - 1)

rec(5)
"""
    res_g = run_single("recursion.py", g_code)
    g_file_g = next(g for g in res_g.graphs.values() if g.graph_type == "file")
    category_tests["G_recursion"] = {
        "file_view_nodes": [(n.node_type, n.label) for n in g_file_g.nodes],
    }

    # Category H: Unsupported Features (Classes)
    print("Testing Category H: Classes & Partial Failure...")
    h_good = FileInput(file_id="h_good", file_name="math_util.py", file_path="math_util.py",
                       file_content="def add(a, b):\n    return a + b\n")
    h_bad = FileInput(file_id="h_bad", file_name="cls.py", file_path="cls.py",
                      file_content="class Greeter:\n    def greet(self):\n        return 'hello'\ng = Greeter()\n")
    res_h = run_pipeline([h_good, h_bad], project_id="h_class_proj")
    category_tests["H_classes"] = {
        "project_status": res_h.status,
        "file_statuses": {f.file_name: f.status for f in res_h.files},
        "diagnostics": [(d.file_id, d.code, d.message) for d in res_h.diagnostics],
    }

    # Category I: Syntax Errors
    print("Testing Category I: Syntax Errors...")
    i_good = FileInput(file_id="i_good", file_name="valid.py", file_path="valid.py",
                       file_content="def valid():\n    return 10\n")
    i_bad = FileInput(file_id="i_bad", file_name="syntax_err.py", file_path="syntax_err.py",
                      file_content="def broken(x):\n    try:\n        return x\n    except ValueError\n        return None\n")
    res_i = run_pipeline([i_good, i_bad], project_id="i_syntax_proj")
    category_tests["I_syntax_errors"] = {
        "project_status": res_i.status,
        "file_statuses": {f.file_name: f.status for f in res_i.files},
        "diagnostics": [(d.file_id, d.code, d.message, d.source_location.start_line if d.source_location else None) for d in res_i.diagnostics],
    }

    # Compile comprehensive audit output
    audit_report = {
        "full_stress_project": full_results,
        "stress_individual_files": stress_files_results,
        "categories": category_tests,
    }

    out_file = out_dir / "audit_results.json"
    out_file.write_text(json.dumps(audit_report, indent=2), encoding="utf-8")
    print(f"\nAudit complete! Machine-readable results saved to: {out_file}")


if __name__ == "__main__":
    main()
