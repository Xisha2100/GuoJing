import { useCallback, useEffect, useState } from "react";

import { adminApi, isApiError } from "../api/client";
import type { Workspace, WorkspaceSummary } from "../api/types";
import { WorkspaceEditor } from "./WorkspaceEditor";
import { HelpRequestPanel } from "../help/HelpRequestPanel";

interface WorkspaceDashboardProps {
  onUnauthorized: () => void;
}

export function WorkspaceDashboard({
  onUnauthorized,
}: WorkspaceDashboardProps) {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [selected, setSelected] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [templates, setTemplates] = useState<{ template_id: string }[]>([]);
  const [error, setError] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setWorkspaces(await adminApi.listWorkspaces());
    } catch (caught) {
      if (isApiError(caught, 401)) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "无法读取工作区。");
    } finally {
      setLoading(false);
    }
  }, [onUnauthorized]);

  useEffect(() => {
    let active = true;
    adminApi
      .listWorkspaces()
      .then((workspaceResult) => {
        if (active) {
          setWorkspaces(workspaceResult);
        }
      })
      .catch((caught: unknown) => {
        if (!active) {
          return;
        }
        if (isApiError(caught, 401)) {
          onUnauthorized();
          return;
        }
        setError(caught instanceof Error ? caught.message : "无法读取工作区。");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [onUnauthorized]);

  async function openWorkspace(workspaceId: string) {
    setError(null);
    try {
      setSelected(await adminApi.getWorkspace(workspaceId));
    } catch (caught) {
      if (isApiError(caught, 401)) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "无法打开工作区。");
    }
  }

  async function createWorkspace() {
    setCreating(true);
    setError(null);
    try {
      setSelected(await adminApi.createWorkspace());
    } catch (caught) {
      if (isApiError(caught, 401)) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "无法新建工作区。");
    } finally {
      setCreating(false);
    }
  }

  async function importTemplate(templateId: string) {
    setCreating(true);
    setError(null);
    try {
      setSelected(await adminApi.importTemplate(templateId));
    } catch (caught) {
      if (isApiError(caught, 401)) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "无法导入模板。");
    } finally {
      setCreating(false);
    }
  }

  async function loadTemplates() {
    setError(null);
    try {
      setTemplates(await adminApi.listTutorialTemplates());
    } catch (caught) {
      if (isApiError(caught, 401)) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "无法读取模板目录。");
    }
  }

  if (selected !== null) {
    return (
      <WorkspaceEditor
        initialWorkspace={selected}
        onUnauthorized={onUnauthorized}
        onBack={() => {
          setSelected(null);
          void loadList();
        }}
      />
    );
  }

  return (
    <>
      <HelpRequestPanel onUnauthorized={onUnauthorized} />
      <section className="dashboard" aria-labelledby="workspace-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">教程生产</p>
            <h2 id="workspace-title">教程工作区</h2>
            <p className="muted">
              保存未完成内容，校验通过后再提升为正式修订。
            </p>
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => void createWorkspace()}
            disabled={creating}
          >
            {creating ? "正在新建…" : "＋ 新建工作区"}
          </button>
        </div>

        {templates.length > 0 ? (
          <div className="template-panel" aria-label="教程模板">
            <p className="eyebrow">快速开始</p>
            <div className="template-actions">
              {templates.map((template) => (
                <button
                  className="secondary-button"
                  type="button"
                  key={template.template_id}
                  disabled={creating}
                  onClick={() => void importTemplate(template.template_id)}
                >
                  导入 {template.template_id}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <button
            className="secondary-button"
            type="button"
            disabled={creating}
            onClick={() => void loadTemplates()}
          >
            从模板开始
          </button>
        )}

        {error !== null && (
          <p className="notice notice-error" role="alert">
            {error}
          </p>
        )}
        {loading ? (
          <p className="loading-message">正在读取工作区…</p>
        ) : workspaces.length === 0 ? (
          <div className="empty-state">
            <h3>还没有教程工作区</h3>
            <p>新建一个空工作区，从目标 APP 和教程标题开始填写。</p>
          </div>
        ) : (
          <div className="workspace-grid">
            {workspaces.map((workspace) => (
              <article className="workspace-card" key={workspace.workspace_id}>
                <div>
                  <span className="status-pill">版本 {workspace.version}</span>
                  <h3>{workspace.title ?? "未命名教程"}</h3>
                  <p className="workspace-id">
                    {workspace.graph_id ?? workspace.workspace_id}
                  </p>
                </div>
                <div className="card-footer">
                  <span>{formatTimestamp(workspace.updated_at)}</span>
                  <button
                    type="button"
                    onClick={() => void openWorkspace(workspace.workspace_id)}
                  >
                    打开编辑
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
