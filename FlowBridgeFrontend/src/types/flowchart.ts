export interface SourceFile {
  fileId?: string;
  fileID?: string;
  fileName?: string;
  filePath?: string;
  path?: string;
  content?: string;
  fileContent?: string;
  byteSize?: number;
}

export interface PyProject {
  id?: string;
  projectID: string;
  name?: string;
  projectName: string;
  files: SourceFile[];
}

export interface FileMetadata {
  fileId: string;
  fileName: string;
  filePath: string;
  graphId: string;
  status: "complete" | "failed" | "unsupported";
}

export interface FunctionInfo {
  functionId: string;
  functionName: string;
  fileId: string;
  startLine: number;
  startColumn?: number;
  endLine: number;
  endColumn?: number;
  graphId: string;
  status: "complete" | "failed";
}

export interface SourceLocation {
  fileId: string;
  startLine: number;
  startColumn: number;
  endLine: number;
  endColumn: number;
}

export interface FlowNode {
  nodeId: string;
  nodeType: "start" | "end" | "statement" | "condition" | "function" | "loop" | "return" | "file";
  label: string;
  sourceLocation?: SourceLocation;
}

export interface FlowEdge {
  edgeId: string;
  sourceId: string;
  targetId: string;
  edgeType: "next" | "true" | "false" | "return";
  label?: string;
}

export interface GraphModel {
  graphId: string;
  graphType: "project" | "file" | "function";
  status: "complete" | "failed";
  fileId?: string;
  functionId?: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface GraphReference {
  sourceGraphId: string;
  sourceNodeId: string;
  targetGraphId: string;
}

export interface FlowchartPayload {
  projectId: string;
  projectName: string;
  revisionId: number;
  status: string;
  files: FileMetadata[];
  functions: FunctionInfo[];
  graphs: Record<string, GraphModel>;
  graphReferences: GraphReference[];
}

export interface SourceSpanDto {
  fileId: string;
  filePath: string;
  startLine: number;
  startColumn: number;
  endLine: number;
  endColumn: number;
}

export interface NodeSourceMappingDto {
  nodeId: string;
  graphId: string;
  nodeType: string;
  label: string;
  span?: SourceSpanDto | null;
  targetGraphId?: string | null;
  targetFileId?: string | null;
  targetFunctionName?: string | null;
}

export interface FileSourceIndexDto {
  fileId: string;
  filePath: string;
  lineToNodes: Record<string, string[]>;
  nodeToSpan: Record<string, SourceSpanDto>;
}

export interface SourceMappingPayload {
  projectId: string;
  files: Record<string, FileSourceIndexDto>;
  nodes: Record<string, NodeSourceMappingDto>;
}

export interface BreadcrumbItem {
  id: string;
  label: string;
  type: "project" | "file" | "function";
  fileId?: string;
  functionId?: string;
}
