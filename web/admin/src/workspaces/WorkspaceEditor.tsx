import { useState } from "react";

import { adminApi, isApiError } from "../api/client";
import type { Readiness, Workspace } from "../api/types";
import { formatDocument, parseTutorialDocument } from "./document";

interface WorkspaceEditorProps {
  initialWorkspace: Workspace;
  onBack: () => void;
  onUnauthorized: () => void;
}

export function WorkspaceEditor({
  initialWorkspace,
  onBack,
  onUnauthorized,
}: WorkspaceEditorProps) {
  const [workspace, setWorkspace] = useState(initialWorkspace);
  const [source, setSource] = useState(() =>
    formatDocument(initialWorkspace.document),
  );
  const [dirty, setDirty] = useState(false);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (caught) {
      if (isApiError(caught, 401)) {
        onUnauthorized();
        return;
      }
      if (isApiError(caught, 409)) {
        setError(
          "该工作区已在其他页面被更新。请重新载入后再编辑，避免覆盖他人的修改。",
        );
        return;
      }
      setError(
        caught instanceof Error ? caught.message : "操作失败，请稍后重试。",
      );
    } finally {
      setBusy(false);
    }
  }

  function save() {
    void run(async () => {
      const document = parseTutorialDocument(source);
      const updated = await adminApi.replaceWorkspace(
        workspace.workspace_id,
        workspace.version,
        document,
      );
      setWorkspace(updated);
      setSource(formatDocument(updated.document));
      setDirty(false);
      setReadiness(null);
      setNotice(`已保存为版本 ${updated.version}。`);
    });
  }

  function validate() {
    void run(async () => {
      const result = await adminApi.validateWorkspace(workspace.workspace_id);
      setReadiness(result);
      setNotice(
        result.ready
          ? "校验通过，可以提升为正式修订。"
          : "校验完成，请处理下列问题。",
      );
    });
  }

  function promote() {
    void run(async () => {
      const result = await adminApi.promoteWorkspace(
        workspace.workspace_id,
        workspace.version,
      );
      setWorkspace(result.workspace);
      setSource(formatDocument(result.workspace.document));
      setReadiness(null);
      setNotice(
        `已生成 ${result.graph_id} 的正式修订 #${result.revision_number}，尚未公开发布。`,
      );
    });
  }

  function reload() {
    void run(async () => {
      const current = await adminApi.getWorkspace(workspace.workspace_id);
      setWorkspace(current);
      setSource(formatDocument(current.document));
      setDirty(false);
      setReadiness(null);
      setNotice(`已重新载入版本 ${current.version}。`);
    });
  }

  return (
    <section className="editor-page" aria-labelledby="editor-title">
      <div className="editor-toolbar">
        <button className="text-button" type="button" onClick={onBack}>
          ← 返回工作区
        </button>
        <div className="toolbar-actions">
          <button type="button" onClick={reload} disabled={busy}>
            重新载入
          </button>
          <button
            className="primary-button"
            type="button"
            onClick={save}
            disabled={busy || !dirty}
          >
            保存
          </button>
          <button type="button" onClick={validate} disabled={busy || dirty}>
            校验
          </button>
          <button
            className="danger-button"
            type="button"
            onClick={promote}
            disabled={busy || dirty || readiness?.ready !== true}
          >
            提升为正式修订
          </button>
        </div>
      </div>

      <div className="editor-heading">
        <div>
          <p className="eyebrow">工作区 · 版本 {workspace.version}</p>
          <h2 id="editor-title">
            {workspace.document.graph.title ?? "未命名教程"}
          </h2>
        </div>
        <span
          className={`status-pill ${dirty ? "status-warning" : "status-saved"}`}
        >
          {dirty ? "有未保存修改" : "已保存"}
        </span>
      </div>

      <p className="muted">
        当前为完整 JSON
        编辑模式。先保存，再校验；只有校验通过的版本才能提升，提升后仍需单独发布。
      </p>

      {notice !== null && (
        <p className="notice notice-success" role="status">
          {notice}
        </p>
      )}
      {error !== null && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}

      <label className="editor-label" htmlFor="document-source">
        教程工作区文档
      </label>
      <textarea
        id="document-source"
        className="json-editor"
        spellCheck={false}
        value={source}
        onChange={(event) => {
          setSource(event.target.value);
          setDirty(true);
          setReadiness(null);
        }}
      />

      {readiness !== null && (
        <section className="readiness-panel" aria-labelledby="readiness-title">
          <h3 id="readiness-title">校验结果</h3>
          {readiness.ready ? (
            <p className="success-text">没有发现阻塞问题。</p>
          ) : (
            <ul className="issue-list">
              {readiness.issues.map((issue, index) => (
                <li key={`${issue.code}-${index}`}>
                  <strong>{issue.code}</strong>
                  <span>{issue.message}</span>
                  {issue.path !== null && <code>{issue.path}</code>}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </section>
  );
}
