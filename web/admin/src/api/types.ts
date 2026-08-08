export type JsonPrimitive = boolean | number | string | null;
export type JsonValue =
  JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface AdminSession {
  user_id: string;
  username: string;
  expires_at: string;
}

export interface TutorialDraftDocument {
  schema_version: "1.0";
  graph: {
    graph_id: string | null;
    title: string | null;
    recorded_app: JsonValue;
    start_node_id: string | null;
    nodes: JsonValue[];
    transitions: JsonValue[];
    [key: string]: JsonValue;
  };
  captures: JsonValue[];
}

export interface WorkspaceSummary {
  workspace_id: string;
  version: number;
  graph_id: string | null;
  title: string | null;
  updated_at: string;
  promoted_graph_id: string | null;
  promoted_revision_number: number | null;
}

export interface Workspace {
  workspace_id: string;
  version: number;
  document: TutorialDraftDocument;
  created_at: string;
  updated_at: string;
  promoted_graph_id: string | null;
  promoted_revision_number: number | null;
}

export interface ReadinessIssue {
  code: string;
  message: string;
  path: string | null;
  node_id: string | null;
  transition_id: string | null;
}

export interface Readiness {
  workspace_id: string;
  version: number;
  ready: boolean;
  issues: ReadinessIssue[];
}

export interface Promotion {
  workspace: Workspace;
  graph_id: string;
  revision_number: number;
  created_at: string;
}
