# FlowBridge — Diagram Renderer Architecture & Hierarchical Navigation Plan

**Author / Proposer:** FlowBridge Team<br>
**Target Audience:** Core Development Team (Visualization, Source Mapping, Parsing & Analysis, Backend & Web)<br>
**Status:** Proposal & Architectural Specification<br>
**Date:** November 2026

---

## 1. Executive Summary & Vision

The core mission of **FlowBridge** is to make unfamiliar codebases immediately understandable by converting static code into clear, interactive, and navigable visual flowcharts.

As codebases grow, attempting to generate or render an entire repository in a single monolithic flowchart creates an unreadable "spaghetti diagram" and chokes layout engines. To solve this, our proposed strategy introduces a **hierarchical, multi-level organization** that processes and visualizes code at three distinct zoom levels:

```
[Level 1: Project View]  ──(Drill down)──>  [Level 2: File View]  ──(Drill down)──>  [Level 3: Function View (CFG)]
```

By pre-organizing the raw output of the Parsing & Analysis pipeline into a structured hierarchical tree, we enable:
1. **Targeted, level-by-level rendering** without overwhelming the user or browser memory.
2. **Seamless navigation** linking parent components to child flowcharts via `graphReferences`.
3. **Deep interactivity**, including bi-directional source code highlighting and clean diagram export capabilities.

---

## 2. Why This Approach? (Motivation & Rationale)

### 2.1 The Problem with Flat/Monolithic Flowcharts
* **Visual & Cognitive Overload:** A repository with 10 files and 50 functions contains hundreds of branching decisions. Rendering everything at once produces visual clutter that obscures architectural logic.
* **Layout Engine Bottlenecks:** Graph layout algorithms (Dagre, Sugiyama, ELK) have $O(V \cdot E)$ or higher computational complexity. Computing crossing minimization and rank assignment for thousands of nodes simultaneously leads to severe browser lag or crashes.
* **Mismatched Developer Mental Model:** Software engineers naturally think hierarchically:
  1. *Architecture Level:* "What files and modules exist, and how are they connected?"
  2. *Module Level:* "What functions and classes are defined in this file?"
  3. *Logic Level:* "What does this specific function do step-by-step?"

### 2.2 Why Hierarchical Organization Works
* **Scalability:** Whether a project has 3 files or 300 files, the renderer only ever renders one focused graph at a time.
* **Semantic Drill-Down:** Users can explore architecture top-down (Project $\to$ File $\to$ Function) or jump directly to any function.
* **Direct Alignment with the Analysis Contract:** Our parsing module already outputs distinct `graphType` values (`"project"`, `"file"`, `"function"`) and cross-graph navigation pointers (`graphReferences`). Our proposal bridges this backend data contract directly to the UI rendering engine.

---

## 3. System Architecture & Processing Pipeline

The proposed pipeline processes the flowchart data in five clear stages:

```
1. Parsing & Analysis Pipeline (Produces raw ProjectAnalysis / Flowchart JSON)
   │
   ▼
2. Graph Organizer & Hierarchy Normalizer (Restructures flat dictionary into hierarchical tree)
   │
   ▼
3. Level-by-Level Diagram Renderer (Calculates layout & node positions on demand)
   │
   ▼
4. Graph Reference & Drill-Down Binder (Attaches navigation triggers between graphs)
   │
   ▼
5. UI View Orchestration & Interactive Canvas (Breadcrumbs, Zoom/Pan, Code Sync, Export)
```

---

### Step 1: The Graph Organizer (Data Normalization Layer)

The raw JSON from the analysis engine provides a flat `graphs` map where graph IDs are opaque hash strings, along with arrays for `files`, `functions`, and `graphReferences`.

The **Graph Organizer** transforms this raw payload into an indexed, hierarchical object model before rendering:

```typescript
// Proposed Hierarchical Tree Structure
export interface HierarchicalProjectModel {
  projectId: string;
  projectName: string;
  projectGraphId: string;
  files: HierarchicalFile[];
}

export interface HierarchicalFile {
  fileId: string;
  fileName: string;
  filePath: string;
  fileGraphId: string;
  functions: HierarchicalFunction[];
}

export interface HierarchicalFunction {
  functionId: string;
  functionName: string;
  qualifiedName: string;
  functionGraphId: string;
  startLine: number;
  endLine: number;
}
```

#### Responsibilities of the Organizer:
1. **Isolate Views:** Identify root graph (`graphType: "project"`), file-level graphs (`graphType: "file"`), and individual function control flow graphs (`graphType: "function"`).
2. **Build Bidirectional Indexing:** Construct fast lookup maps:
   - `nodeToChildGraph: Map<nodeId, targetGraphId>` (from `graphReferences`)
   - `childGraphToParent: Map<childGraphId, { parentGraphId, parentNodeId }>`
   - `graphToSourceFile: Map<graphId, fileId>`

---

### Step 2: Level-by-Level Diagram Renderer

Rather than generating all diagrams at once, the diagram renderer processes **one graph level at a time**:

| View Level | Nodes Represent | Edges Represent | Interactivity / Click Action |
| :--- | :--- | :--- | :--- |
| **Level 1: Project View** | Source files (`.py`) | Import / dependency relationships | Clicking a file node drills down into that file's **File View**. |
| **Level 2: File View** | Functions, classes, module top-level code | Call relationships or definition order | Clicking a function node drills down into its **Function View**. |
| **Level 3: Function View (CFG)** | Control flow nodes (`condition`, `statement`, `loop`, `return`) | Directed branches (`next`, `true`, `false`, `back`, `return`) | Clicking a node highlights the corresponding lines in the **Source Code Viewer**. |

#### Layout Algorithm Principles:
* **Directed Acyclic Graph (DAG) Layering:** Use hierarchical layering (Sugiyama / Dagre layout).
* **Loop / Cycle Handling:** In function CFGs, loop iterations produce `back` edges. These edges are detected and excluded during layer calculation to guarantee a clean top-to-bottom layout, then rendered as curved return loops.

---

### Step 3: Graph Reference Linking & Breadcrumb Navigation

Using the `graphReferences` provided by analysis:
* Each node in the Project or File view is checked against the navigation index.
* If a node targets another graph, the renderer displays an **expand / drill-down icon** (e.g., `🔍 View Details` or `➔`).
* The UI maintains a navigation stack:
  ```
  [Project: MyCalculator]  >  [File: calculator.py]  >  [Function: add()]
  ```
* Clicking any previous breadcrumb instantly returns to that view without re-running parsing or resetting canvas state.

---

## 4. Frontend UI Integration & Interactive Features

The user interface integrates the renderer alongside the source code viewer in a split-screen or coordinated layout.

### 4.1 Interactive Canvas
* **Zoom & Pan:** Canvas controls (mouse-wheel zoom, click-and-drag panning, "Fit to Screen" button) for smooth navigation across large diagrams.
* **Visual Node Distinctiveness:**
  - `start` / `end`: Rounded pill shapes (Green / Gray).
  - `condition`: Diamond / angled shapes (Amber/Orange).
  - `statement`: Clean rounded rectangles (Blue / Slate).
  - `return`: Distinct terminal accent color.

### 4.2 Bi-Directional Source Code Highlighting (Coordination with Grace)
Interactivity between the diagram and source code is essential:
1. **Flowchart $\to$ Code:**
   - Every node carries `sourceLocation: { fileId, startLine, startColumn, endLine, endColumn }`.
   - When a user clicks a node, the UI notifies the `SourceCodeViewer`, which auto-scrolls to and highlights the corresponding line numbers.
2. **Code $\to$ Flowchart:**
   - When a user clicks a line of code in the code viewer, the diagram identifies the matching node and applies an active ring/glow effect.

### 4.3 Diagram Exporting
Because the flowchart is rendered as structured vector data (SVG/Canvas):
* **One-Click Export:** Users can export the currently displayed diagram as **SVG** (crisp, scalable vector) or **PNG** (image for slides/docs).
* **Export Payload:** Optionally export the clean graph JSON structure for offline tooling or reporting.

---

## 5. Team Module Responsibilities & Collaboration

To ensure smooth teamwork, here is how this architecture interfaces with each module owner:

| Team Member | Module | Integration Interface & Expectations |
| :--- | :--- | :--- |
| **Justin** | Code Manager | Provides validated `SourceFile` snapshots, `fileId`, `fileName`, `filePath`, and decoded `fileContent`. |
| **Parsing & Analysis** | AST & CFG Engine | Generates `ProjectAnalysis` JSON containing `graphs`, `graphReferences`, `files`, `functions`, and diagnostics. |
| **Kevin** | Visualization (Renderer) | Implements the **Graph Organizer** and **Hierarchical Renderer**, handles DAG layout coordinates, node styling, zoom/pan, and SVG/PNG export. |
| **Grace** | Source Mapping & Navigation | Consumes `sourceLocation` and `graphReferences` to power the bidirectional click-to-highlight sync between diagram nodes and the code editor. |
| **Jerry** | Website & Layout | Embeds the viewer component into the FlowBridge web layout, manages responsive sizing, export modals, and control buttons. |

---

## 6. Recommended Next Steps

1. **Review & Team Feedback:** Team members review the proposed three-level model and confirm interface contracts.
2. **Build the Hierarchy Organizer Helper:** Implement the lightweight normalization helper function that indexes `graphs` and `graphReferences` by level.
3. **Refine Renderer Component:** Adapt the layout engine to render Level 1 (Project), Level 2 (File), and Level 3 (Function) cleanly with custom node shapes.
4. **Wire Source Highlight Hook:** Connect the node selection event to the existing source code viewer component.
