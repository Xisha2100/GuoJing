import type {
  AdminSession,
  Promotion,
  Readiness,
  TutorialDraftDocument,
  Workspace,
  WorkspaceSummary,
} from "./types";

const ADMIN_API = "/api/v1/admin";
const CSRF_COOKIE = "guojing_admin_csrf";
const CSRF_HEADER = "X-CSRF-Token";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(readErrorMessage(detail, status));
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  requiresCsrf = false,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (requiresCsrf) {
    const csrfToken = readCookie(CSRF_COOKIE);
    if (csrfToken === null) {
      throw new ApiError(403, "浏览器中没有 CSRF Cookie，请重新登录。");
    }
    headers.set(CSRF_HEADER, csrfToken);
  }

  const response = await fetch(`${ADMIN_API}${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 204) {
    if (!response.ok) {
      throw new ApiError(response.status, null);
    }
    return undefined as T;
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      isObject(payload) && "detail" in payload ? payload.detail : payload;
    throw new ApiError(response.status, detail);
  }
  return payload as T;
}

export const adminApi = {
  login(username: string, password: string): Promise<AdminSession> {
    return request<AdminSession>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
  },

  me(): Promise<AdminSession> {
    return request<AdminSession>("/auth/me");
  },

  logout(): Promise<void> {
    return request<void>("/auth/logout", { method: "POST" }, true);
  },

  listWorkspaces(): Promise<WorkspaceSummary[]> {
    return request<WorkspaceSummary[]>("/tutorial-drafts");
  },

  createWorkspace(): Promise<Workspace> {
    return request<Workspace>(
      "/tutorial-drafts",
      { method: "POST", body: JSON.stringify({}) },
      true,
    );
  },

  getWorkspace(workspaceId: string): Promise<Workspace> {
    return request<Workspace>(
      `/tutorial-drafts/${encodeURIComponent(workspaceId)}`,
    );
  },

  replaceWorkspace(
    workspaceId: string,
    expectedVersion: number,
    document: TutorialDraftDocument,
  ): Promise<Workspace> {
    return request<Workspace>(
      `/tutorial-drafts/${encodeURIComponent(workspaceId)}`,
      {
        method: "PUT",
        body: JSON.stringify({ expected_version: expectedVersion, document }),
      },
      true,
    );
  },

  validateWorkspace(workspaceId: string): Promise<Readiness> {
    return request<Readiness>(
      `/tutorial-drafts/${encodeURIComponent(workspaceId)}/validate`,
      { method: "POST" },
      true,
    );
  },

  promoteWorkspace(
    workspaceId: string,
    expectedVersion: number,
  ): Promise<Promotion> {
    return request<Promotion>(
      `/tutorial-drafts/${encodeURIComponent(workspaceId)}/promote`,
      {
        method: "POST",
        body: JSON.stringify({ expected_version: expectedVersion }),
      },
      true,
    );
  },
};

export function isApiError(error: unknown, status?: number): error is ApiError {
  return (
    error instanceof ApiError &&
    (status === undefined || error.status === status)
  );
}

function readCookie(name: string): string | null {
  const encodedName = `${encodeURIComponent(name)}=`;
  for (const part of document.cookie.split(";")) {
    const cookie = part.trim();
    if (cookie.startsWith(encodedName)) {
      return decodeURIComponent(cookie.slice(encodedName.length));
    }
  }
  return null;
}

function readErrorMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (isObject(detail) && typeof detail.message === "string") {
    return detail.message;
  }
  if (Array.isArray(detail) && detail.length > 0 && isObject(detail[0])) {
    const firstMessage = detail[0].message ?? detail[0].msg;
    if (typeof firstMessage === "string") {
      return firstMessage;
    }
  }
  return `请求失败（HTTP ${status}）`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
