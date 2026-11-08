"""Diagram Renderer Execution Runner.

Generates the complete hierarchical diagram directory with SVG diagrams
and an interactive HTML drill-down viewer.
"""

import json
from pathlib import Path
from typing import Any

from .layout import SugiyamaDAGLayout
from .models import HierarchicalProjectModel, RenderedGraph
from .organizer import GraphOrganizer
from .renderer import DiagramRenderer


class HierarchicalDiagramPipeline:
    """End-to-end pipeline executing the 5-step diagram renderer architecture."""

    def __init__(self, output_dir: str = "rendered_diagrams") -> None:
        self.output_dir = Path(output_dir)
        self.organizer = GraphOrganizer()
        self.layout_engine = SugiyamaDAGLayout()
        self.renderer = DiagramRenderer()

    def run(self, analysis_data: dict[str, Any]) -> HierarchicalProjectModel:
        """Process the analysis payload and emit hierarchical SVGs + interactive viewer."""
        # 1. Organize into hierarchical tree model
        model = self.organizer.organize(analysis_data)

        flowchart = analysis_data.get("flowchart", analysis_data)
        raw_graphs: dict[str, Any] = flowchart.get("graphs", {})

        self.output_dir.mkdir(parents=True, exist_ok=True)
        rendered_graphs: list[RenderedGraph] = []
        exports = []

        # 2. Render Level 1: Project View
        if model.project_graph_id in raw_graphs:
            proj_data = raw_graphs[model.project_graph_id]
            proj_rendered = self.layout_engine.layout(
                graph_data=proj_data,
                title=f"Project View — {model.project_name}",
                child_lookup=model.node_to_child_graph,
            )
            self.renderer.to_svg(proj_rendered)
            rendered_graphs.append(proj_rendered)

            proj_svg_path = self.output_dir / "project_view.svg"
            proj_svg_path.write_text(proj_rendered.svg_content, encoding="utf-8")
            exports.append({"graphId": model.project_graph_id, "path": "project_view.svg"})

        # 3. Render Level 2: File Views & Level 3: Function Views
        files_dir = self.output_dir / "files"
        files_dir.mkdir(exist_ok=True)

        # Export paths use stable list positions so duplicate names and opaque IDs cannot collide.
        for file_index, f in enumerate(model.files):
            safe_fname = f"file_{file_index:04d}"
            f_dir = files_dir / safe_fname
            f_dir.mkdir(exist_ok=True)

            # Render File View
            if f.file_graph_id in raw_graphs:
                f_data = raw_graphs[f.file_graph_id]
                f_rendered = self.layout_engine.layout(
                    graph_data=f_data,
                    title=f"File View — {f.file_path}",
                    child_lookup=model.node_to_child_graph,
                )
                self.renderer.to_svg(f_rendered)
                rendered_graphs.append(f_rendered)

                file_svg_path = f_dir / "file_view.svg"
                file_svg_path.write_text(f_rendered.svg_content, encoding="utf-8")
                exports.append(
                    {
                        "graphId": f.file_graph_id,
                        "filePath": f.file_path,
                        "path": file_svg_path.relative_to(self.output_dir).as_posix(),
                    }
                )

            # Render Function Views
            if f.functions:
                funcs_dir = f_dir / "functions"
                funcs_dir.mkdir(exist_ok=True)

                for function_index, fn in enumerate(f.functions):
                    if fn.function_graph_id in raw_graphs:
                        fn_data = raw_graphs[fn.function_graph_id]
                        fn_rendered = self.layout_engine.layout(
                            graph_data=fn_data,
                            title=f"Function View — {fn.function_name}() ({f.file_path}:{fn.start_line})",
                            child_lookup=model.node_to_child_graph,
                        )
                        self.renderer.to_svg(fn_rendered)
                        rendered_graphs.append(fn_rendered)

                        safe_fn_name = f"function_{function_index:04d}"
                        fn_svg_path = funcs_dir / f"{safe_fn_name}.svg"
                        fn_svg_path.write_text(fn_rendered.svg_content, encoding="utf-8")
                        exports.append(
                            {
                                "graphId": fn.function_graph_id,
                                "filePath": f.file_path,
                                "path": fn_svg_path.relative_to(self.output_dir).as_posix(),
                            }
                        )

        # Keep module views available in the exported viewer as well as the React interface.
        modules_dir = self.output_dir / "modules"
        for index, graph_data in enumerate(raw_graphs.values()):
            if graph_data.get("graphType") == "module":
                modules_dir.mkdir(exist_ok=True)
                rendered = self.layout_engine.layout(
                    graph_data=graph_data,
                    title="Module View",
                    child_lookup=model.node_to_child_graph,
                )
                self.renderer.to_svg(rendered)
                rendered_graphs.append(rendered)
                svg_path = modules_dir / f"module_{index:04d}.svg"
                svg_path.write_text(rendered.svg_content, encoding="utf-8")
                exports.append(
                    {
                        "graphId": rendered.graph_id,
                        "path": svg_path.relative_to(self.output_dir).as_posix(),
                    }
                )

        # 4. Generate Interactive Viewer
        html_viewer = self.renderer.generate_html_viewer(model.project_name, rendered_graphs)
        html_path = self.output_dir / "interactive_viewer.html"
        html_path.write_text(html_viewer, encoding="utf-8")
        (self.output_dir / "index.html").write_text(html_viewer, encoding="utf-8")
        for entry in exports:
            entry["status"] = raw_graphs[entry["graphId"]].get("status", "complete")
        (self.output_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "projectId": model.project_id,
                    "revisionId": flowchart.get("revisionId"),
                    "graphs": exports,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        print("=" * 70)
        print(" FlowBridge Diagram Renderer Pipeline Complete!")
        print("=" * 70)
        print(f"Hierarchical Output Directory: {self.output_dir.resolve()}")
        print(f"  * Level 1: Project View SVG:     {self.output_dir / 'project_view.svg'}")
        print(f"  * Level 2 & 3: File & Func SVGs: {files_dir}")
        print(f"  * Interactive Browser Viewer:   {html_path}")
        print("=" * 70)

        return model
