"""Hierarchical DAG layout engine (Sugiyama-style) with loop and back-edge routing."""

from typing import Any

from .models import RenderedEdge, RenderedGraph, RenderedNode


class SugiyamaDAGLayout:
    """Computes coordinate positions for nodes and routes edges hierarchically."""

    def __init__(
        self,
        node_sep: float = 40.0,
        rank_sep: float = 70.0,
        default_node_height: float = 48.0,
        char_width: float = 8.5,
        min_node_width: float = 120.0,
    ) -> None:
        self.node_sep = node_sep
        self.rank_sep = rank_sep
        self.default_node_height = default_node_height
        self.char_width = char_width
        self.min_node_width = min_node_width

    def _estimate_size(self, node: dict[str, Any]) -> tuple[float, float]:
        label = node.get("label", "")
        ntype = node.get("nodeType", "statement")

        # Determine width
        text_len = max(len(line) for line in label.split("\n")) if label else 4
        width = max(self.min_node_width, text_len * self.char_width + 36.0)

        # Determine height
        line_count = len(label.split("\n")) if label else 1
        height = max(self.default_node_height, line_count * 20.0 + 20.0)

        if ntype in ("start", "end"):
            width = max(100.0, text_len * self.char_width + 30.0)
            height = 42.0
        elif ntype == "condition":
            width = max(130.0, text_len * self.char_width + 48.0)
            height = max(54.0, line_count * 22.0 + 24.0)

        return width, height

    def layout(
        self,
        graph_data: dict[str, Any],
        title: str,
        child_lookup: dict[tuple[str, str], str],
    ) -> RenderedGraph:
        raw_nodes = graph_data.get("nodes", [])
        raw_edges = graph_data.get("edges", [])
        graph_id = graph_data.get("graphId", "graph")
        if graph_data.get("status", "complete") != "complete":
            title = f"{title} ({graph_data['status']})"
        graph_type = graph_data.get("graphType", "function")

        if not raw_nodes:
            return RenderedGraph(
                graph_id=graph_id,
                graph_type=graph_type,
                title=title,
                width=400.0,
                height=200.0,
                nodes=[],
                edges=[],
            )

        # 1. Size calculation
        sizes: dict[str, tuple[float, float]] = {}
        for n in raw_nodes:
            nid = n["nodeId"]
            sizes[nid] = self._estimate_size(n)

        # 2. Separate forward edges and back/loop edges
        forward_edges: list[dict[str, Any]] = []
        back_edges: list[dict[str, Any]] = []

        # Build adjacency
        adj: dict[str, list[str]] = {n["nodeId"]: [] for n in raw_nodes}
        for e in raw_edges:
            src, tgt = e.get("sourceId"), e.get("targetId")
            if e.get("edgeType") == "back":
                back_edges.append(e)
            else:
                forward_edges.append(e)
                if src in adj:
                    adj[src].append(tgt)

        # Cycle detection on forward edges to guarantee DAG
        visited: dict[str, int] = {}  # 0: visiting, 1: visited
        acyclic_edges: list[dict[str, Any]] = []

        def dfs(u: str):
            visited[u] = 0
            for e in [ed for ed in forward_edges if ed.get("sourceId") == u]:
                v = e.get("targetId")
                if v not in visited:
                    acyclic_edges.append(e)
                    dfs(v)
                elif visited[v] == 1:
                    acyclic_edges.append(e)
                else:
                    # Found cycle -> treat as back edge
                    back_edges.append(e)
            visited[u] = 1

        for n in raw_nodes:
            nid = n["nodeId"]
            if nid not in visited:
                dfs(nid)

        # 3. Layer assignment (Longest path ranking on DAG)
        in_degree: dict[str, int] = {n["nodeId"]: 0 for n in raw_nodes}
        dag_adj: dict[str, list[str]] = {n["nodeId"]: [] for n in raw_nodes}
        for e in acyclic_edges:
            src, tgt = e.get("sourceId"), e.get("targetId")
            if src in dag_adj and tgt in in_degree:
                dag_adj[src].append(tgt)
                in_degree[tgt] += 1

        # Queue roots
        rank: dict[str, int] = {nid: 0 for nid in in_degree}
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        if not queue:
            queue = [raw_nodes[0]["nodeId"]]

        # Topological traversal for rank
        topo_order = []
        q = list(queue)
        temp_in = dict(in_degree)
        while q:
            u = q.pop(0)
            topo_order.append(u)
            for v in dag_adj.get(u, []):
                rank[v] = max(rank[v], rank[u] + 1)
                temp_in[v] -= 1
                if temp_in[v] == 0:
                    q.append(v)

        # Assign isolated or unreached nodes
        for n in raw_nodes:
            nid = n["nodeId"]
            if nid not in rank:
                rank[nid] = 0

        # Group nodes by rank
        ranks: dict[int, list[str]] = {}
        for nid, r in rank.items():
            ranks.setdefault(r, []).append(nid)

        # 4. Position calculation (X and Y coordinates)
        node_coords: dict[str, tuple[float, float]] = {}
        max_rank = max(ranks.keys()) if ranks else 0
        current_y = 60.0  # Top margin

        max_graph_width = 400.0

        for r in range(max_rank + 1):
            nodes_in_rank = ranks.get(r, [])
            if not nodes_in_rank:
                continue

            max_h = max(sizes[nid][1] for nid in nodes_in_rank)
            total_rank_w = (
                sum(sizes[nid][0] for nid in nodes_in_rank)
                + (len(nodes_in_rank) - 1) * self.node_sep
            )
            max_graph_width = max(max_graph_width, total_rank_w + 120.0)

            # Center nodes horizontally
            current_x = (max_graph_width - total_rank_w) / 2.0

            for nid in nodes_in_rank:
                w, h = sizes[nid]
                node_coords[nid] = (current_x, current_y)
                current_x += w + self.node_sep

            current_y += max_h + self.rank_sep

        graph_height = current_y + 40.0
        graph_width = max_graph_width + 80.0

        # 5. Build RenderedNodes
        rendered_nodes: list[RenderedNode] = []
        for n in raw_nodes:
            nid = n["nodeId"]
            x, y = node_coords.get(nid, (50.0, 50.0))
            w, h = sizes[nid]
            child_graph = child_lookup.get((graph_id, nid))

            rendered_nodes.append(
                RenderedNode(
                    node_id=nid,
                    label=n.get("label", ""),
                    node_type=n.get("nodeType", "statement"),
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    source_location=n.get("sourceLocation"),
                    target_graph_id=child_graph,
                    is_clickable=child_graph is not None,
                )
            )

        # 6. Route edges (RenderedEdges)
        rendered_edges: list[RenderedEdge] = []
        all_edges = acyclic_edges + back_edges

        for e in all_edges:
            eid = e.get("edgeId", f"e_{len(rendered_edges)}")
            src_id, tgt_id = e.get("sourceId"), e.get("targetId")
            if src_id not in node_coords or tgt_id not in node_coords:
                continue

            sx, sy = node_coords[src_id]
            sw, sh = sizes[src_id]
            tx, ty = node_coords[tgt_id]
            tw, th = sizes[tgt_id]
            etype = e.get("edgeType", "next")
            is_back = (etype == "back") or (rank.get(tgt_id, 0) <= rank.get(src_id, 0))

            if is_back:
                # Curved routing around the right side of the diagram
                start_pt = (sx + sw, sy + sh / 2.0)
                loop_x = max(sx + sw, tx + tw) + 45.0
                pt1 = (loop_x, sy + sh / 2.0)
                pt2 = (loop_x, ty + th / 2.0)
                end_pt = (tx + tw, ty + th / 2.0)
                points = [start_pt, pt1, pt2, end_pt]
            else:
                # Top-to-bottom routing
                start_pt = (sx + sw / 2.0, sy + sh)
                end_pt = (tx + tw / 2.0, ty)
                if abs(start_pt[0] - end_pt[0]) < 5.0:
                    points = [start_pt, end_pt]
                else:
                    mid_y = (start_pt[1] + end_pt[1]) / 2.0
                    points = [start_pt, (start_pt[0], mid_y), (end_pt[0], mid_y), end_pt]

            rendered_edges.append(
                RenderedEdge(
                    edge_id=eid,
                    source_id=src_id,
                    target_id=tgt_id,
                    edge_type=etype,
                    label=e.get("label"),
                    points=points,
                    is_back_edge=is_back,
                )
            )

        return RenderedGraph(
            graph_id=graph_id,
            graph_type=graph_type,
            title=title,
            width=graph_width,
            height=graph_height,
            nodes=rendered_nodes,
            edges=rendered_edges,
        )
