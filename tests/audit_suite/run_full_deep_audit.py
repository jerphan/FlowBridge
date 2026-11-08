"""Comprehensive Deep Audit & Verification Script for FlowBridge_Complex_Test_Project.

Runs the full 15-file project and each file individually through the entire
FlowBridge pipeline (Parsing, Feature Validation, AST Analysis, Call Resolution,
CFG Generation, Project Graph Assembly, and Backend Diagram Rendering).
"""
import json
import os
from pathlib import Path

from flowbridge_analysis import ParsingAnalysisService
from flowbridge_analysis.models import FileInput, ProjectInput
from FlowBridgeBackend.diagram_renderer.runner import HierarchicalDiagramPipeline

root = Path(__file__).resolve().parents[2]


def load_stress_files(stress_dir: Path) -> list[FileInput]:
    files = []
    for r, _, filenames in os.walk(stress_dir):
        for fname in sorted(filenames):
            if fname.endswith(".py"):
                full_p = Path(r) / fname
                rel_p = str(full_p.relative_to(stress_dir)).replace("\\", "/")
                content = full_p.read_text(encoding="utf-8")
                files.append(FileInput(
                    file_id=f"f_{len(files)}",
                    file_name=fname,
                    file_path=rel_p,
                    file_content=content,
                ))
    return files


def run():
    stress_dir = root / "tests" / "temp_complex_project" / "FlowBridge_Stress_Project"
    files = load_stress_files(stress_dir)
    print(f"Loaded {len(files)} Python files from {stress_dir.name}:")
    for f in files:
        print(f"  - [{f.file_id}] {f.file_path} ({len(f.file_content.splitlines())} lines)")

    service = ParsingAnalysisService()

    # 1. Full Multi-File Project Analysis
    print("\n" + "=" * 60)
    print("1. RUNNING FULL MULTI-FILE PROJECT ANALYSIS")
    print("=" * 60)

    proj_input = ProjectInput(
        project_id="stress_full",
        project_name="FlowBridge Complex Stress Project",
        revision_id=1,
        files=files,
    )
    result = service.analyze_project(proj_input.to_dict())

    print(f"Project Status: {result.status.upper()}")
    print(f"Total Files Analyzed: {len(result.files)}")
    print(f"Total Functions Extracted: {len(result.functions)}")
    print(f"Total Graphs Generated: {len(result.graphs)}")
    print(f"Total Graph References (Navigation Links): {len(result.graph_references)}")
    print(f"Total Call References Analyzed: {len(result.call_references)}")
    print(f"Total Source Mappings: {len(result.source_mappings)}")
    print(f"Total Diagnostics: {len(result.diagnostics)}")

    # Resolution breakdown
    res_counts = {}
    for c in result.call_references:
        res_counts[c.resolution] = res_counts.get(c.resolution, 0) + 1
    print("\nCall Resolution Breakdown:")
    for status, count in sorted(res_counts.items()):
        print(f"  - {status}: {count}")

    # File Status Breakdown
    print("\nPer-File Statuses in Full Project:")
    file_statuses = {}
    for f in result.files:
        print(f"  - {f.file_path:<35}: {f.status.upper()}")
        file_statuses[f.file_path] = f.status

    # 2. Individual File Analysis
    print("\n" + "=" * 60)
    print("2. RUNNING ISOLATED INDIVIDUAL FILE ANALYSIS")
    print("=" * 60)

    individual_results = {}
    for f in files:
        single_input = ProjectInput(
            project_id=f"proj_{f.file_id}",
            project_name=f"Single File {f.file_name}",
            revision_id=1,
            files=[f],
        )
        single_res = service.analyze_project(single_input.to_dict())
        meta = single_res.files[0]
        node_types = set()
        edge_types = set()
        for g in single_res.graphs.values():
            for n in g.nodes:
                node_types.add(n.node_type)
            for e in g.edges:
                edge_types.add(e.edge_type)

        diag_codes = [d.code for d in single_res.diagnostics]
        individual_results[f.file_path] = {
            "status": meta.status,
            "graphs_count": len(single_res.graphs),
            "node_types": sorted(list(node_types)),
            "edge_types": sorted(list(edge_types)),
            "diagnostics": diag_codes,
            "call_references": len(single_res.call_references),
        }
        print(f"  - {f.file_path:<35}: {meta.status.upper()} | {len(single_res.graphs)} graphs | NodeTypes: {sorted(list(node_types))}")

    # 3. Backend Diagram Rendering Check
    print("\n" + "=" * 60)
    print("3. RUNNING BACKEND DIAGRAM RENDERER PIPELINE")
    print("=" * 60)

    try:
        pipeline = HierarchicalDiagramPipeline(output_dir=str(root / "tests" / "audit_suite" / "rendered_stress_diagrams"))
        model = pipeline.run(result.to_dict())
        print("Renderer Result: SUCCESS!")
        print(f"Total Rendered Graphs: {len(pipeline.rendered_graphs)}")
        print(f"Clickable Nodes across all diagrams: {len(model.node_to_child_graph)}")
    except Exception as ex:
        print(f"Renderer FAILED: {ex}")
        raise

    # 4. Save detailed report
    report_path = root / "tests" / "audit_suite" / "full_deep_audit_results.json"
    report_data = {
        "full_project": {
            "status": result.status,
            "files_count": len(result.files),
            "file_statuses": file_statuses,
            "functions_count": len(result.functions),
            "graphs_count": len(result.graphs),
            "graph_references_count": len(result.graph_references),
            "call_references_count": len(result.call_references),
            "call_resolution_breakdown": res_counts,
            "diagnostics_count": len(result.diagnostics),
            "diagnostics": [
                {
                    "severity": d.severity,
                    "code": d.code,
                    "file_id": d.file_id,
                    "message": d.message,
                    "line": d.source_location.start_line if d.source_location else None,
                }
                for d in result.diagnostics
            ],
        },
        "individual_files": individual_results,
        "renderer": {
            "status": "success",
            "rendered_graphs_count": len(pipeline.rendered_graphs),
            "clickable_nodes_count": len(model.node_to_child_graph),
        },
    }
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    print(f"\nSaved full deep audit data to: {report_path}")


if __name__ == "__main__":
    run()
