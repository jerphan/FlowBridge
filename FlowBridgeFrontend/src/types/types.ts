export interface sourceFile{
    fileID : string;
    fileName : string;
    filePath : string;
    fileContent : string;
}

export interface pyProject{
    projectID : string;
    projectName : string;
    files : sourceFile[];
}

export interface errorDetail{
    code : string;
    message : string;
    filePath? : string | null;
}

export interface errorResponse{
    error : errorDetail;
}

export type uploadStatus = "idle" | "uploading" | "success" | "error";

export interface sourceLocation{
    fileId : string;
    startLine : number;
    endLine : number;
    startColumn : number;
    endColumn : number;
}

export type graphType = "project" | "file" | "function" | "module";
export type graphStatus = "complete" | "unsupported" | "failed";

export interface fileMetadata{
    fileId : string;
    fileName : string;
    filePath : string;
    graphId : string;
    status : graphStatus;
}

export interface flowNode{
    nodeId : string;
    nodeType : string;
    label : string;
    sourceLocation : sourceLocation | null;
}

export interface flowEdge{
    edgeId : string;
    sourceId : string;
    targetId : string;
    edgeType : string;
    label : string | null;
}

export interface flowGraph{
    graphId : string;
    graphType : graphType;
    status : graphStatus;
    fileId : string | null;
    functionId : string | null;
    nodes : flowNode[];
    edges : flowEdge[];
}

export interface graphReference{
    sourceGraphId : string;
    sourceNodeId : string;
    targetGraphId : string;
}

export interface parameterInfo{
    name : string;
    kind : string;
    hasDefault : boolean;
    annotation : string | null;
}

export interface functionInfo{
    functionId : string;
    functionName : string;
    qualifiedName : string;
    fileId : string;
    parameters : parameterInfo[];
    startLine : number;
    endLine : number;
    startColumn : number;
    endColumn : number;
    graphId : string;
    scopeId : string;
}

export interface callReference{
    callId : string;
    fileId : string;
    callerFunctionId : string | null;
    location : sourceLocation;
    expression : string;
    resolution : string;
    targetFunctionId : string | null;
    targetGraphId : string | null;
    reason : string;
}

export interface symbolInfo{
    scopeId : string;
    name : string;
    kind : string;
    fileId : string;
    location : sourceLocation | null;
    functionId : string | null;
    importTarget : string | null;
}

export interface diagnostic{
    severity : "info" | "warning" | "error";
    code : string;
    message : string;
    fileId : string | null;
    sourceLocation : sourceLocation | null;
    graphId : string | null;
}

export interface flowchartJSON{
    projectId : string | null;
    projectName : string | null;
    revisionId : number | null;
    status : "success" | "partial" | "failed";
    files : fileMetadata[];
    functions : functionInfo[];
    graphs : Record<string, flowGraph>;
    graphReferences : graphReference[];
    callReferences : callReference[];
    symbols : symbolInfo[];
    diagnostics : diagnostic[];
}

export type FlowchartJSON = flowchartJSON;

export interface SourceSelection {
    projectId: string;
    revisionId: number;
    location: sourceLocation;
    file: sourceFile;
}

export interface RenderResult {
    projectId: string;
    revisionId: number;
    status: 'success' | 'partial' | 'failed';
    fileCount: number;
    viewerUrl: string;
    manifestUrl: string;
}
