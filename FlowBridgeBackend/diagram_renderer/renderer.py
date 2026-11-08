"""SVG Diagram Renderer and HTML Viewer Generator for FlowBridge."""
import html
from typing import Any, Dict, List
from .models import RenderedGraph, RenderedNode, RenderedEdge


class DiagramRenderer:
    """Renders structured diagrams into standalone SVG files and interactive HTML viewers."""

    def to_svg(self, graph: RenderedGraph) -> str:
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {graph.width:.1f} {graph.height:.1f}" '
            f'width="{graph.width:.1f}" height="{graph.height:.1f}" class="flowbridge-diagram">',
            """<defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#1a73e8" />
    </marker>
    <marker id="arrow-true" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#2e7d32" />
    </marker>
    <marker id="arrow-false" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill="#c62828" />
    </marker>
    <filter id="nodeShadow" x="-5%" y="-5%" width="110%" height="115%">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.08"/>
    </filter>
  </defs>
  <style>
    .node-text { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; font-size: 13px; text-anchor: middle; dominant-baseline: middle; fill: #212529; }
    .node-subtext { font-family: sans-serif; font-size: 11px; fill: #6c757d; text-anchor: middle; }
    .edge-line { fill: none; stroke: #1a73e8; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
    .edge-true { stroke: #2e7d32; }
    .edge-false { stroke: #c62828; }
    .edge-back { stroke: #e65100; stroke-dasharray: 4,3; }
    .edge-label { font-family: sans-serif; font-size: 11px; font-weight: 600; fill: #495057; text-anchor: middle; }
    .clickable { cursor: pointer; transition: transform 0.15s, filter 0.15s; }
    .clickable:hover { filter: brightness(0.95); }
  </style>""",
            f'  <text x="{graph.width / 2.0:.1f}" y="28" font-family="sans-serif" font-size="16" font-weight="bold" '
            f'text-anchor="middle" fill="#1f2937">{html.escape(graph.title)}</text>',
        ]

        # 1. Render Edges
        for edge in graph.edges:
            svg_parts.append(self._render_edge(edge))

        # 2. Render Nodes
        for node in graph.nodes:
            svg_parts.append(self._render_node(node))

        svg_parts.append("</svg>")
        svg_content = "\n".join(svg_parts)
        graph.svg_content = svg_content
        return svg_content

    def _render_edge(self, edge: RenderedEdge) -> str:
        pts = edge.points
        if not pts:
            return ""

        marker = "url(#arrow)"
        cls = "edge-line"
        if edge.edge_type == "true":
            marker = "url(#arrow-true)"
            cls += " edge-true"
        elif edge.edge_type == "false":
            marker = "url(#arrow-false)"
            cls += " edge-false"
        elif edge.is_back_edge:
            cls += " edge-back"

        path_d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
        for pt in pts[1:]:
            path_d += f" L {pt[0]:.1f} {pt[1]:.1f}"

        edge_svg = f'  <path d="{path_d}" class="{cls}" marker-end="{marker}" />'

        # Label
        lbl = edge.label or (edge.edge_type if edge.edge_type in ("true", "false") else None)
        if lbl and len(pts) >= 2:
            mid_idx = len(pts) // 2
            mx = (pts[mid_idx - 1][0] + pts[mid_idx][0]) / 2.0
            my = (pts[mid_idx - 1][1] + pts[mid_idx][1]) / 2.0 - 5.0
            edge_svg += f'\n  <rect x="{mx - 18:.1f}" y="{my - 9:.1f}" width="36" height="15" fill="#ffffff" rx="3" opacity="0.9"/>'
            edge_svg += f'\n  <text x="{mx:.1f}" y="{my + 2:.1f}" class="edge-label">{html.escape(lbl)}</text>'

        return edge_svg

    def _render_node(self, node: RenderedNode) -> str:
        x, y, w, h = node.x, node.y, node.width, node.height
        cx, cy = x + w / 2.0, y + h / 2.0
        label_text = html.escape(node.label)
        click_attr = f' class="clickable" onclick="onNodeDrillDown(\'{node.target_graph_id}\')"' if node.is_clickable else ""

        node_body = []
        node_body.append(f'  <g id="{node.node_id}"{click_attr}>')

        if node.node_type == "start":
            node_body.append(f'    <rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h/2.0:.1f}" fill="#e8f5e9" stroke="#2e7d32" stroke-width="2" filter="url(#nodeShadow)"/>')
            node_body.append(f'    <text x="{cx:.1f}" y="{cy:.1f}" class="node-text" fill="#1b5e20" font-weight="600">{label_text}</text>')

        elif node.node_type == "end":
            node_body.append(f'    <rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{h/2.0:.1f}" fill="#eceff1" stroke="#455a64" stroke-width="2" filter="url(#nodeShadow)"/>')
            node_body.append(f'    <text x="{cx:.1f}" y="{cy:.1f}" class="node-text" fill="#263238" font-weight="600">{label_text}</text>')

        elif node.node_type == "condition":
            # Diamond shape
            pts = f"{cx:.1f},{y:.1f} {x+w:.1f},{cy:.1f} {cx:.1f},{y+h:.1f} {x:.1f},{cy:.1f}"
            node_body.append(f'    <polygon points="{pts}" fill="#fff8e1" stroke="#f57f17" stroke-width="2" filter="url(#nodeShadow)"/>')
            node_body.append(f'    <text x="{cx:.1f}" y="{cy:.1f}" class="node-text" fill="#e65100" font-weight="600">{label_text}</text>')

        elif node.node_type == "return":
            # Terminal return shape
            node_body.append(f'    <rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="#fbe9e7" stroke="#d84315" stroke-width="1.8" filter="url(#nodeShadow)"/>')
            node_body.append(f'    <text x="{cx:.1f}" y="{cy:.1f}" class="node-text" fill="#bf360c">{label_text}</text>')

        elif node.node_type == "file":
            # File card shape
            node_body.append(f'    <rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="#e3f2fd" stroke="#1976d2" stroke-width="2" filter="url(#nodeShadow)"/>')
            node_body.append(f'    <text x="{cx:.1f}" y="{cy - 5:.1f}" class="node-text" font-weight="600" fill="#0d47a1">📄 {label_text}</text>')
            if node.is_clickable:
                node_body.append(f'    <text x="{cx:.1f}" y="{cy + 13:.1f}" class="node-subtext" fill="#1565c0">🔍 View File Flowchart ➔</text>')

        elif node.node_type == "function":
            # Function block with drilldown indication
            fill = "#e0f2f1" if node.is_clickable else "#f3e5f5"
            stroke = "#00796b" if node.is_clickable else "#7b1fa2"
            node_body.append(f'    <rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2" filter="url(#nodeShadow)"/>')
            icon = "⚡ "
            y_offset = -6 if node.is_clickable else 0
            node_body.append(f'    <text x="{cx:.1f}" y="{cy + y_offset:.1f}" class="node-text" font-weight="600" fill="{stroke}">{icon}{label_text}</text>')
            if node.is_clickable:
                node_body.append(f'    <text x="{cx:.1f}" y="{cy + 12:.1f}" class="node-subtext" fill="{stroke}">🔍 Drill Down ➔</text>')

        else:
            # Standard statement
            node_body.append(f'    <rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="#f8f9fa" stroke="#495057" stroke-width="1.5" filter="url(#nodeShadow)"/>')
            node_body.append(f'    <text x="{cx:.1f}" y="{cy:.1f}" class="node-text">{label_text}</text>')

        node_body.append("  </g>")
        return "\n".join(node_body)

    def generate_html_viewer(self, project_name: str, rendered_graphs: List[RenderedGraph]) -> str:
        """Assembles all rendered SVGs into a single interactive browser viewer."""
        graphs_json = []
        for g in rendered_graphs:
            graphs_json.append({
                "id": g.graph_id,
                "type": g.graph_type,
                "title": g.title,
                "svg": g.svg_content,
            })

        import json
        graphs_payload = json.dumps(graphs_json)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FlowBridge — {html.escape(project_name)}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      margin: 0; padding: 0; background: #f4f6f8; color: #212529; display: flex; flex-direction: column; height: 100vh;
    }}
    header {{
      background: #1a73e8; color: white; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    .breadcrumbs {{
      background: #ffffff; border-bottom: 1px solid #e0e0e0; padding: 10px 24px; display: flex; align-items: center; gap: 8px; font-size: 14px;
    }}
    .breadcrumb-item {{
      color: #1a73e8; cursor: pointer; font-weight: 500;
    }}
    .breadcrumb-item:hover {{ text-decoration: underline; }}
    .breadcrumb-item.active {{ color: #212529; font-weight: 600; cursor: default; text-decoration: none; }}
    .separator {{ color: #9e9e9e; }}
    .main-canvas {{
      flex: 1; overflow: auto; padding: 24px; display: flex; justify-content: center; align-items: flex-start;
    }}
    .svg-container {{
      background: #ffffff; padding: 24px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); max-width: 100%;
    }}
    .toolbar {{
      position: fixed; bottom: 24px; right: 24px; display: flex; gap: 10px; background: white; padding: 8px 12px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }}
    .btn {{
      background: #1a73e8; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;
    }}
    .btn:hover {{ background: #1557b0; }}
  </style>
</head>
<body>
  <header>
    <h3 style="margin:0;">FlowBridge Visualizer — {html.escape(project_name)}</h3>
    <span id="levelIndicator" style="font-size: 14px; opacity: 0.9;">Project View</span>
  </header>
  
  <div class="breadcrumbs" id="breadcrumbs">
    <!-- Breadcrumbs populated dynamically -->
  </div>

  <div class="main-canvas">
    <div class="svg-container" id="svgContainer"></div>
  </div>

  <div class="toolbar">
    <button class="btn" onclick="exportCurrentSVG()">📥 Export SVG</button>
  </div>

  <script>
    const graphs = {graphs_payload};
    let graphMap = new Map(graphs.map(g => [g.id, g]));
    let navStack = [];

    // Find root project graph or first graph
    let rootGraph = graphs.find(g => g.type === 'project') || graphs[0];

    function navigateTo(graphId) {{
      const graph = graphMap.get(graphId);
      if (!graph) return;

      // Update stack
      const existingIdx = navStack.indexOf(graphId);
      if (existingIdx !== -1) {{
        navStack = navStack.slice(0, existingIdx + 1);
      }} else {{
        navStack.push(graphId);
      }}

      renderCurrentGraph();
    }}

    function renderCurrentGraph() {{
      const currentId = navStack[navStack.length - 1];
      const g = graphMap.get(currentId);
      if (!g) return;

      document.getElementById('svgContainer').innerHTML = g.svg;
      document.getElementById('levelIndicator').innerText = g.type.toUpperCase() + " VIEW";

      // Render breadcrumbs
      const bc = document.getElementById('breadcrumbs');
      bc.innerHTML = navStack.map((gid, idx) => {{
        const item = graphMap.get(gid);
        const isLast = idx === navStack.length - 1;
        const name = item.title.split(' — ')[1] || item.title;
        if (isLast) {{
          return `<span class="breadcrumb-item active">${{name}}</span>`;
        }}
        return `<span class="breadcrumb-item" onclick="navigateTo('${{gid}}')">${{name}}</span><span class="separator">/</span>`;
      }}).join('');
    }}

    function onNodeDrillDown(targetGraphId) {{
      if (targetGraphId && graphMap.has(targetGraphId)) {{
        navigateTo(targetGraphId);
      }}
    }}

    function exportCurrentSVG() {{
      const currentId = navStack[navStack.length - 1];
      const g = graphMap.get(currentId);
      if (!g) return;
      const blob = new Blob([g.svg], {{ type: 'image/svg+xml' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${{g.title.replace(/[^a-zA-Z0-9]/g, '_')}}.svg`;
      a.click();
    }}

    if (rootGraph) {{
      navigateTo(rootGraph.id);
    }}
  </script>
</body>
</html>
"""
