import type {
  AdminSession,
  TutorialDraftDocument,
  Workspace,
} from "../api/types";

export const adminSession: AdminSession = {
  user_id: "admin-1",
  username: "family-admin",
  expires_at: "2026-08-08T18:00:00Z",
};

export const emptyDocument: TutorialDraftDocument = {
  schema_version: "1.0",
  graph: {
    graph_id: null,
    title: null,
    recorded_app: null,
    start_node_id: null,
    nodes: [],
    transitions: [],
  },
  captures: [],
};

export function workspace(version = 1): Workspace {
  return {
    workspace_id: "workspace-1",
    version,
    document: emptyDocument,
    created_at: "2026-08-08T10:00:00Z",
    updated_at: "2026-08-08T10:00:00Z",
    promoted_graph_id: null,
    promoted_revision_number: null,
  };
}

export function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
