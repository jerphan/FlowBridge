"""CLI entrypoint for running the diagram renderer."""

import argparse
import json
import sys
from pathlib import Path

# Add project roots
repo_root = Path(__file__).resolve().parent.parent.parent
analysis_src = repo_root / "FlowBridge_ParsingAndAnalysis" / "src"
if str(analysis_src) not in sys.path:
    sys.path.insert(0, str(analysis_src))

from flowbridge_analysis import ParsingAnalysisService  # noqa: E402

from .runner import HierarchicalDiagramPipeline  # noqa: E402


def get_default_sample():
    return {
        "projectId": "P-CALC",
        "projectName": "FlowBridge Demo Calculator",
        "revisionId": 1,
        "files": [
            {
                "fileId": "F1",
                "fileName": "calculator.py",
                "filePath": "calculator.py",
                "fileContent": (
                    "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"
                ),
            },
            {
                "fileId": "F2",
                "fileName": "main.py",
                "filePath": "main.py",
                "fileContent": (
                    "from calculator import add\n\n"
                    "def calculate():\n"
                    "    x = 10\n"
                    "    y = 20\n"
                    "    return x + y\n\n"
                    "def main():\n"
                    "    result = calculate()\n"
                    "    total = add(result, 5)\n"
                    "    print(total)\n\n"
                    "main()\n"
                ),
            },
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="FlowBridge Hierarchical Diagram Renderer")
    parser.add_argument("--input", "-i", help="Path to flowchart.json or analysis.json")
    parser.add_argument(
        "--out", "-o", default="rendered_diagrams", help="Output directory for SVGs and HTML"
    )
    args = parser.parse_args()

    if args.input:
        in_path = Path(args.input)
        if not in_path.exists():
            print(f"Error: Input file '{in_path}' does not exist.")
            sys.exit(1)
        data = json.loads(in_path.read_text(encoding="utf-8"))
    else:
        print("No input provided; generating fresh analysis with built-in multi-level sample...")
        sample_payload = get_default_sample()
        service = ParsingAnalysisService()
        result = service.analyze_project(sample_payload)
        data = result.to_dict()

    pipeline = HierarchicalDiagramPipeline(output_dir=args.out)
    pipeline.run(data)


if __name__ == "__main__":
    main()
