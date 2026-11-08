"""Hierarchical DAG layout engine (Sugiyama-style) with loop and back-edge routing."""
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from .models import RenderedNode, RenderedEdge, RenderedGraph


class SugiyamaDAGLayout:
    """Computes coordinate positions for nodes and routes edges hierarchically."""

    def __init__(
        self,
        node_sep: float = 45.0,
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

    def _estimate_size(self, node: Dict[str, Any]) -> Tuple[float, float]:
        label = node.get("label", "")
        ntype = node.get("nodeType", "statement")
        
        # Determine width
        text_len = max(len(line) for line in label.split("\n")) if label else 4
        width = max(self.min_node_width, text_len * self.char_width + 36.0)

        # Determine height
        line_count = len(label.split("\n")) if label else 1
        height = max(self.default_node_height, line_count * 20.0 + 20.0)

        if ntype in ("start", "end"):
            width = max(110.0, text_len * self.char_width + 36.0)
            height = 42.0
        elif ntype == "condition":
            width = max(140.0, text_len * self.char_width + 48.0)
            height = max(56.0, line_count * 22.0 + 26.0)
        elif ntype == "file":
            width = max(200.0, text_len * self.char_width + 40.0)
            height = 62.0
        elif ntype == "function":
            width = max(150.0, text_len * self.char_width + 44.0)
            height = 54.0
        elif ntype == "return":
            width = max(120.0, text_len * self.char_width + 36.0)
            height = 46.0

        return width, height

    def layout(
        self,
        graph_data: Dict[str, Any],
        title: str,
        child_lookup: Dict[str, str],
        file_statuses: Optional[Dict[str, str]] = None,
    ) -> RenderedGraph:
        raw_nodes = graph_data.get("nodes", [])
        raw_edges = graph_data.get("edges", [])
        graph_id = graph_data.get("graphId", "graph")
        graph_type = graph_data.get("graphType", "function")
        file_status_map = file_statuses or {}

        if not raw_nodes:
            return RenderedGraph(
                graph_id=graph_id,
                graph_type=graph_type,
                title=title,
                width=450.0,
                height=220.0,
                nodes=[],
                edges=[],
            )

        # 1. Size calculation
        sizes: Dict[str, Tuple[float, float]] = {}
        for n in raw_nodes:
            nid = n["nodeId"]
            sizes[nid] = self._estimate_size(n)

        # -------------------------------------------------------------
        # SPECIAL CASE: Project View (Organized dependency hierarchy + compact grid)
        # -------------------------------------------------------------
        if graph_type == "project":
            return self._layout_project_view(
                graph_data=graph_data,
                title=title,
                child_lookup=child_lookup,
                sizes=sizes,
                file_status_map=file_status_map,
            )

        # -------------------------------------------------------------
        # STANDARD CFG LAYOUT (File View and Function View)
        # -------------------------------------------------------------
        # 2. Separate forward edges and back/loop edges
        forward_edges: List[Dict[str, Any]] = []
        back_edges: List[Dict[str, Any]] = []
        
        adj: Dict[str, List[str]] = {n["nodeId"]: [] for n in raw_nodes}
        for e in raw_edges:
            src, tgt = e.get("sourceId"), e.get("targetId")
            if e.get("edgeType") == "back":
                back_edges.append(e)
            else:
                forward_edges.append(e)
                if src in adj:
                    adj[src].append(tgt)

        # Cycle detection to guarantee DAG
        visited: Dict[str, int] = {}
        acyclic_edges: List[Dict[str, Any]] = []

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
                    back_edges.append(e)
            visited[u] = 1

        # Visit start node first if present to preserve canonical execution flow
        start_nodes = [n["nodeId"] for n in raw_nodes if n.get("nodeType") == "start"]
        for sn in start_nodes:
            if sn not in visited:
                dfs(sn)

        for n in raw_nodes:
            nid = n["nodeId"]
            if nid not in visited:
                dfs(nid)

        # 3. Layer assignment (Longest path ranking on DAG)
        in_degree: Dict[str, int] = {n["nodeId"]: 0 for n in raw_nodes}
        dag_adj: Dict[str, List[str]] = {n["nodeId"]: [] for n in raw_nodes}
        for e in acyclic_edges:
            src, tgt = e.get("sourceId"), e.get("targetId")
            if src in dag_adj and tgt in in_degree:
                dag_adj[src].append(tgt)
                in_degree[tgt] += 1

        rank: Dict[str, int] = {nid: 0 for nid in in_degree}

        # Rule 1: Start Node Position — Start node always rank 0
        if start_nodes:
            start_id = start_nodes[0]
            queue = [start_id]
            # Other nodes with in_degree == 0 will start after start node
            for nid, deg in in_degree.items():
                if deg == 0 and nid != start_id:
                    queue.append(nid)
        else:
            queue = [nid for nid, deg in in_degree.items() if deg == 0]
            if not queue:
                queue = [raw_nodes[0]["nodeId"]]

        # Topological traversal for longest path rank
        q = list(queue)
        temp_in = dict(in_degree)
        while q:
            u = q.pop(0)
            for v in dag_adj.get(u, []):
                rank[v] = max(rank[v], rank[u] + 1)
                temp_in[v] -= 1
                if temp_in[v] == 0:
                    q.append(v)

        # Ensure all nodes other than start node have rank >= 1 if start node exists
        if start_nodes:
            start_id = start_nodes[0]
            rank[start_id] = 0
            for nid in rank:
                if nid != start_id and rank[nid] == 0 and nid in dag_adj.get(start_id, []):
                    rank[nid] = 1

        # Rule 2: End/Stop Node Position — End node strictly at bottom when reachable
        end_nodes = [n["nodeId"] for n in raw_nodes if n.get("nodeType") == "end"]
        for end_id in end_nodes:
            # Check if this end node has incoming edges (is reachable)
            incoming = [e for e in acyclic_edges if e.get("targetId") == end_id]
            if incoming:
                max_other_rank = max((r for nid, r in rank.items() if nid != end_id), default=0)
                rank[end_id] = max(rank.get(end_id, 0), max_other_rank + 1)

        # Assign any unreached nodes
        for n in raw_nodes:
            nid = n["nodeId"]
            if nid not in rank:
                rank[nid] = 0

        # Group nodes by rank
        ranks: Dict[int, List[str]] = {}
        for nid, r in rank.items():
            ranks.setdefault(r, []).append(nid)

        max_rank = max(ranks.keys()) if ranks else 0

        # -------------------------------------------------------------
        # Crossing Reduction & Symmetrical Branching
        # -------------------------------------------------------------
        # Map condition edges for symmetrical ordering: True left, False right
        condition_true_targets: Dict[str, str] = {}
        condition_false_targets: Dict[str, str] = {}
        for e in raw_edges:
            src = e.get("sourceId")
            tgt = e.get("targetId")
            etype = e.get("edgeType")
            if etype == "true":
                condition_true_targets[src] = tgt
            elif etype == "false":
                condition_false_targets[src] = tgt

        # Forward pass: sort nodes in rank r by barycenter of predecessors
        for r in range(1, max_rank + 1):
            nodes_in_rank = ranks.get(r, [])
            if len(nodes_in_rank) <= 1:
                continue

            node_barycenter: Dict[str, float] = {}
            for nid in nodes_in_rank:
                preds = [e.get("sourceId") for e in acyclic_edges if e.get("targetId") == nid]
                valid_preds = [p for p in preds if p in rank and rank[p] < r]
                if valid_preds:
                    bc = sum(ranks[rank[p]].index(p) for p in valid_preds) / len(valid_preds)
                else:
                    bc = float(nodes_in_rank.index(nid))
                node_barycenter[nid] = bc

            nodes_in_rank.sort(key=lambda nid: node_barycenter.get(nid, 0.0))

            # Apply symmetrical condition ordering (True to left, False to right)
            for c_node, t_tgt in condition_true_targets.items():
                f_tgt = condition_false_targets.get(c_node)
                if f_tgt and t_tgt in nodes_in_rank and f_tgt in nodes_in_rank:
                    idx_t = nodes_in_rank.index(t_tgt)
                    idx_f = nodes_in_rank.index(f_tgt)
                    if idx_t > idx_f:
                        # Swap so True is on left, False is on right
                        nodes_in_rank[idx_f], nodes_in_rank[idx_t] = nodes_in_rank[idx_t], nodes_in_rank[idx_f]

            ranks[r] = nodes_in_rank

        # Backward pass: fine-tune higher ranks based on successor barycenters
        for r in range(max_rank - 1, 0, -1):
            nodes_in_rank = ranks.get(r, [])
            if len(nodes_in_rank) <= 1:
                continue

            node_barycenter_back: Dict[str, float] = {}
            for nid in nodes_in_rank:
                succs = [e.get("targetId") for e in acyclic_edges if e.get("sourceId") == nid]
                valid_succs = [s for s in succs if s in rank and rank[s] > r and s in ranks.get(rank[s], [])]
                if valid_succs:
                    bc = sum(ranks[rank[s]].index(s) for s in valid_succs) / len(valid_succs)
                else:
                    bc = float(nodes_in_rank.index(nid))
                node_barycenter_back[nid] = bc

            nodes_in_rank.sort(key=lambda nid: node_barycenter_back.get(nid, 0.0))
            ranks[r] = nodes_in_rank

        # 4. Position calculation (X and Y coordinates)
        node_coords: Dict[str, Tuple[float, float]] = {}
        current_y = 60.0  # Top margin

        # Estimate maximum graph width needed
        max_graph_width = 400.0
        for r in range(max_rank + 1):
            nodes_in_rank = ranks.get(r, [])
            if not nodes_in_rank:
                continue
            total_rank_w = sum(sizes[nid][0] for nid in nodes_in_rank) + (len(nodes_in_rank) - 1) * self.node_sep
            max_graph_width = max(max_graph_width, total_rank_w + 240.0)

        for r in range(max_rank + 1):
            nodes_in_rank = ranks.get(r, [])
            if not nodes_in_rank:
                continue

            max_h = max(sizes[nid][1] for nid in nodes_in_rank)
            total_rank_w = sum(sizes[nid][0] for nid in nodes_in_rank) + (len(nodes_in_rank) - 1) * self.node_sep

            # Center nodes horizontally within this rank
            current_x = (max_graph_width - total_rank_w) / 2.0

            for nid in nodes_in_rank:
                w, h = sizes[nid]
                node_coords[nid] = (current_x, current_y)
                current_x += w + self.node_sep

            current_y += max_h + self.rank_sep

        graph_height = current_y + 40.0
        min_node_left = min((coords[0] for coords in node_coords.values()), default=40.0)
        max_node_right = max((coords[0] + sizes[nid][0] for nid, coords in node_coords.items()), default=max_graph_width)

        # 5. Build RenderedNodes
        rendered_nodes: List[RenderedNode] = []
        for n in raw_nodes:
            nid = n["nodeId"]
            x, y = node_coords.get(nid, (50.0, 50.0))
            w, h = sizes[nid]
            child_graph = child_lookup.get(nid)

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

        # 6. Anti-spaghetti channel routing with dedicated gutters and multi-port separation
        all_edges = acyclic_edges + back_edges

        # Group outgoing edges by source to calculate distinct exit ports
        out_edges_by_src: Dict[str, List[Dict[str, Any]]] = {}
        for e in all_edges:
            out_edges_by_src.setdefault(e.get("sourceId"), []).append(e)

        # Group incoming edges by target to calculate distinct entry ports
        in_edges_by_tgt: Dict[str, List[Dict[str, Any]]] = {}
        for e in all_edges:
            in_edges_by_tgt.setdefault(e.get("targetId"), []).append(e)

        # Classify edges into dedicated tracks
        loop_back_edges = [
            e for e in all_edges
            if e.get("edgeType") == "back" or (rank.get(e.get("targetId"), 0) <= rank.get(e.get("sourceId"), 0))
        ]

        # Exception edges skipping ranks to outer left gutter
        exc_gutter_edges = [
            e for e in all_edges
            if e.get("edgeType") in ("exception", "unhandled")
            and (rank.get(e.get("targetId"), 0) > rank.get(e.get("sourceId"), 0) + 1)
        ]

        # Long-span forward edges (skipping > 1 rank)
        long_fwd_edges = [
            e for e in all_edges
            if e not in loop_back_edges
            and e not in exc_gutter_edges
            and (rank.get(e.get("targetId"), 0) > rank.get(e.get("sourceId"), 0) + 1)
        ]

        rendered_edges: List[RenderedEdge] = []
        center_x = max_graph_width / 2.0

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
            is_back = e in loop_back_edges

            src_node_type = next((n.get("nodeType") for n in raw_nodes if n["nodeId"] == src_id), "statement")
            tgt_node_type = next((n.get("nodeType") for n in raw_nodes if n["nodeId"] == tgt_id), "statement")

            # --- CALCULATE DISTINCT ORIGIN PORT ---
            src_out = out_edges_by_src.get(src_id, [e])
            if src_node_type == "condition":
                if etype == "true":
                    start_pt = (sx, sy + sh / 2.0)  # Left tip of diamond
                elif etype == "false":
                    start_pt = (sx + sw, sy + sh / 2.0)  # Right tip of diamond
                else:
                    start_pt = (sx + sw / 2.0, sy + sh)
            elif any(ed.get("edgeType") in ("true", "false") for ed in src_out):
                # Branching node with true / false
                if etype == "true":
                    start_pt = (sx + sw * 0.25, sy + sh)
                elif etype == "false":
                    start_pt = (sx + sw * 0.75, sy + sh)
                else:
                    start_pt = (sx + sw / 2.0, sy + sh)
            elif len(src_out) > 1:
                # Distribute multiple forward exits evenly
                k = src_out.index(e)
                start_pt = (sx + sw * ((k + 1) / (len(src_out) + 1)), sy + sh)
            else:
                start_pt = (sx + sw / 2.0, sy + sh)

            # --- CALCULATE DISTINCT TARGET PORT ---
            tgt_in = in_edges_by_tgt.get(tgt_id, [e])
            if len(tgt_in) > 1:
                # Sort incoming edges by source X coordinate so they enter side-by-side cleanly
                sorted_in = sorted(tgt_in, key=lambda ed: node_coords.get(ed.get("sourceId"), (0, 0))[0])
                m = sorted_in.index(e)
                end_pt = (tx + tw * ((m + 1) / (len(tgt_in) + 1)), ty)
            else:
                end_pt = (tx + tw / 2.0, ty)

            # --- ROUTING LOGIC ---
            if is_back:
                # 1. Back-edges: dedicated parallel lanes on the RIGHT outer gutter
                lane_idx = loop_back_edges.index(e)
                lane_x = max_node_right + 45.0 + (lane_idx * 28.0)
                down_y = sy + sh + 15.0
                up_y = ty - 15.0
                points = [
                    start_pt,
                    (start_pt[0], down_y),
                    (lane_x, down_y),
                    (lane_x, up_y),
                    (end_pt[0], up_y),
                    end_pt,
                ]

            elif e in exc_gutter_edges:
                # 2. Long-span Exception edges: dedicated parallel lanes on the LEFT outer gutter
                lane_idx = exc_gutter_edges.index(e)
                lane_x = min_node_left - 40.0 - (lane_idx * 25.0)
                down_y = sy + sh + 15.0
                points = [
                    start_pt,
                    (start_pt[0], down_y),
                    (lane_x, down_y),
                    (lane_x, ty - 15.0),
                    (end_pt[0], ty - 15.0),
                    end_pt,
                ]

            elif e in long_fwd_edges:
                # 3. Long-span Forward edges (> 1 rank): route in outer bypass channels
                lane_idx = long_fwd_edges.index(e)
                if start_pt[0] >= center_x:
                    bypass_x = max_node_right + 20.0 + (lane_idx * 22.0)
                else:
                    bypass_x = min_node_left - 20.0 - (lane_idx * 22.0)

                points = [
                    start_pt,
                    (start_pt[0], sy + sh + 15.0),
                    (bypass_x, sy + sh + 15.0),
                    (bypass_x, ty - 15.0),
                    (end_pt[0], ty - 15.0),
                    end_pt,
                ]

            else:
                # 4. Adjacent Rank Edges (1-rank step): route cleanly within the inter-rank gap
                if src_node_type == "condition":
                    mid_y = (sy + sh + ty) / 2.0
                    if etype == "true":
                        points = [
                            start_pt,
                            (start_pt[0] - 15.0, start_pt[1]),
                            (start_pt[0] - 15.0, mid_y),
                            (end_pt[0], mid_y),
                            end_pt,
                        ]
                    elif etype == "false":
                        points = [
                            start_pt,
                            (start_pt[0] + 15.0, start_pt[1]),
                            (start_pt[0] + 15.0, mid_y),
                            (end_pt[0], mid_y),
                            end_pt,
                        ]
                    else:
                        points = [start_pt, (start_pt[0], mid_y), (end_pt[0], mid_y), end_pt]
                else:
                    if abs(start_pt[0] - end_pt[0]) < 6.0:
                        points = [start_pt, end_pt]
                    else:
                        mid_y = (sy + sh + ty) / 2.0
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

        # Shift all coordinates to maintain positive margin if left gutter extends < 40px
        left_ext = min((p[0] for ed in rendered_edges for p in ed.points), default=min_node_left)
        right_ext = max((p[0] for ed in rendered_edges for p in ed.points), default=max_node_right)

        if left_ext < 40.0:
            shift_x = 40.0 - left_ext
            for n in rendered_nodes:
                n.x += shift_x
            for ed in rendered_edges:
                ed.points = [(p[0] + shift_x, p[1]) for p in ed.points]
            total_width = right_ext + shift_x + 60.0
        else:
            total_width = right_ext + 60.0

        return RenderedGraph(
            graph_id=graph_id,
            graph_type=graph_type,
            title=title,
            width=max(max_graph_width, total_width),
            height=graph_height,
            nodes=rendered_nodes,
            edges=rendered_edges,
        )

    def _layout_project_view(
        self,
        graph_data: Dict[str, Any],
        title: str,
        child_lookup: Dict[str, str],
        sizes: Dict[str, Tuple[float, float]],
        file_status_map: Dict[str, str],
    ) -> RenderedGraph:
        """Organizes Project View: connected dependency tree on top, compact grid for standalone files below."""
        raw_nodes = graph_data.get("nodes", [])
        raw_edges = graph_data.get("edges", [])
        graph_id = graph_data.get("graphId", "project_graph")

        all_node_ids = [n["nodeId"] for n in raw_nodes]
        edge_source_ids = {e.get("sourceId") for e in raw_edges}
        edge_target_ids = {e.get("targetId") for e in raw_edges}
        connected_node_ids = [nid for nid in all_node_ids if nid in edge_source_ids or nid in edge_target_ids]
        disconnected_node_ids = [nid for nid in all_node_ids if nid not in connected_node_ids]

        node_coords: Dict[str, Tuple[float, float]] = {}
        max_graph_width = 750.0
        current_y = 65.0

        # Part 1: Connected files hierarchical layout (Importing file -> Imported file)
        if connected_node_ids:
            in_degree: Dict[str, int] = {nid: 0 for nid in connected_node_ids}
            adj: Dict[str, List[str]] = {nid: [] for nid in connected_node_ids}
            for e in raw_edges:
                src, tgt = e.get("sourceId"), e.get("targetId")
                if src in adj and tgt in in_degree:
                    adj[src].append(tgt)
                    in_degree[tgt] += 1

            rank: Dict[str, int] = {nid: 0 for nid in connected_node_ids}
            queue = [nid for nid, deg in in_degree.items() if deg == 0]
            if not queue:
                queue = [connected_node_ids[0]]

            q = list(queue)
            temp_in = dict(in_degree)
            while q:
                u = q.pop(0)
                for v in adj.get(u, []):
                    rank[v] = max(rank[v], rank[u] + 1)
                    temp_in[v] -= 1
                    if temp_in[v] == 0:
                        q.append(v)

            ranks: Dict[int, List[str]] = {}
            for nid, r in rank.items():
                ranks.setdefault(r, []).append(nid)

            max_rank = max(ranks.keys()) if ranks else 0

            # Barycenter ordering for connected ranks
            for r in range(1, max_rank + 1):
                nodes_in_rank = ranks.get(r, [])
                if len(nodes_in_rank) > 1:
                    nodes_in_rank.sort(key=lambda nid: sum(ranks[rank[p]].index(p) for p in in_degree if p in adj and nid in adj[p]) if any(p in adj and nid in adj[p] for p in in_degree) else 0)
                    ranks[r] = nodes_in_rank

            for r in range(max_rank + 1):
                nodes_in_rank = ranks.get(r, [])
                if not nodes_in_rank:
                    continue
                total_w = sum(sizes[nid][0] for nid in nodes_in_rank) + (len(nodes_in_rank) - 1) * self.node_sep
                max_graph_width = max(max_graph_width, total_w + 160.0)

            for r in range(max_rank + 1):
                nodes_in_rank = ranks.get(r, [])
                if not nodes_in_rank:
                    continue
                max_h = max(sizes[nid][1] for nid in nodes_in_rank)
                total_w = sum(sizes[nid][0] for nid in nodes_in_rank) + (len(nodes_in_rank) - 1) * self.node_sep
                cur_x = (max_graph_width - total_w) / 2.0
                for nid in nodes_in_rank:
                    w, h = sizes[nid]
                    node_coords[nid] = (cur_x, current_y)
                    cur_x += w + self.node_sep
                current_y += max_h + self.rank_sep + 15.0

        # Part 2: Disconnected standalone files in a compact grid
        if disconnected_node_ids:
            if connected_node_ids:
                current_y += 35.0  # Section spacing

            cols = min(3, max(1, len(disconnected_node_ids)))
            col_width = 220.0
            row_height = 62.0
            col_gap = 25.0
            row_gap = 20.0

            total_grid_w = cols * col_width + (cols - 1) * col_gap
            max_graph_width = max(max_graph_width, total_grid_w + 140.0)
            start_x = (max_graph_width - total_grid_w) / 2.0

            for idx, nid in enumerate(disconnected_node_ids):
                row = idx // cols
                col = idx % cols
                x = start_x + col * (col_width + col_gap)
                y = current_y + row * (row_height + row_gap)
                sizes[nid] = (col_width, row_height)
                node_coords[nid] = (x, y)

            num_rows = math.ceil(len(disconnected_node_ids) / cols)
            current_y += num_rows * (row_height + row_gap) + 20.0

        # Build RenderedNodes
        rendered_nodes: List[RenderedNode] = []
        for n in raw_nodes:
            nid = n["nodeId"]
            x, y = node_coords.get(nid, (50.0, 50.0))
            w, h = sizes[nid]
            child_graph = child_lookup.get(nid)
            label = n.get("label", "")

            # Determine file status
            status = file_status_map.get(nid) or file_status_map.get(label) or file_status_map.get(child_graph or "") or "complete"

            rendered_nodes.append(
                RenderedNode(
                    node_id=nid,
                    label=label,
                    node_type=n.get("nodeType", "file"),
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                    source_location=n.get("sourceLocation"),
                    target_graph_id=child_graph,
                    is_clickable=child_graph is not None,
                    status=status,
                )
            )

        # Route directed import edges (main.py -> calculator.py)
        rendered_edges: List[RenderedEdge] = []
        for e in raw_edges:
            eid = e.get("edgeId", f"pe_{len(rendered_edges)}")
            src_id, tgt_id = e.get("sourceId"), e.get("targetId")
            if src_id not in node_coords or tgt_id not in node_coords:
                continue

            sx, sy = node_coords[src_id]
            sw, sh = sizes[src_id]
            tx, ty = node_coords[tgt_id]
            tw, th = sizes[tgt_id]

            start_pt = (sx + sw / 2.0, sy + sh)
            end_pt = (tx + tw / 2.0, ty)

            if abs(start_pt[0] - end_pt[0]) < 8.0:
                points = [start_pt, end_pt]
            else:
                mid_y = (start_pt[1] + end_pt[1]) / 2.0
                points = [start_pt, (start_pt[0], mid_y), (end_pt[0], mid_y), end_pt]

            rendered_edges.append(
                RenderedEdge(
                    edge_id=eid,
                    source_id=src_id,
                    target_id=tgt_id,
                    edge_type="next",
                    label=e.get("label", "imports"),
                    points=points,
                    is_back_edge=False,
                )
            )

        return RenderedGraph(
            graph_id=graph_id,
            graph_type="project",
            title=title,
            width=max_graph_width + 40.0,
            height=current_y + 40.0,
            nodes=rendered_nodes,
            edges=rendered_edges,
        )
