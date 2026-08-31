import { useCallback, useState } from "react";

import { adminApi, isApiError } from "../api/client";
import type { HelpRequestReview } from "../api/types";

interface HelpRequestPanelProps {
  onUnauthorized: () => void;
}

export function HelpRequestPanel({ onUnauthorized }: HelpRequestPanelProps) {
  const [items, setItems] = useState<HelpRequestReview[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await adminApi.listHelpRequestReviews());
    } catch (caught) {
      if (isApiError(caught, 401)) return onUnauthorized();
      setError(caught instanceof Error ? caught.message : "无法读取求助队列。");
    }
  }, [onUnauthorized]);

  async function processNext() {
    setProcessing(true);
    setError(null);
    try {
      await adminApi.processNextHelpRequests();
      await load();
    } catch (caught) {
      if (isApiError(caught, 401)) return onUnauthorized();
      setError(caught instanceof Error ? caught.message : "处理求助失败。");
    } finally {
      setProcessing(false);
    }
  }

  return (
    <section className="dashboard" aria-labelledby="help-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">家属协助</p>
          <h2 id="help-title">求助处理</h2>
          <p className="muted">
            这里只展示状态摘要和用户问题，不展示截图或 OCR。
          </p>
        </div>
        <div>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void load()}
          >
            刷新队列
          </button>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void processNext()}
            disabled={processing}
          >
            {processing ? "处理中…" : "处理下一批"}
          </button>
        </div>
      </div>
      {error !== null && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      {items.length === 0 ? (
        <p className="empty-state">当前没有等待人工复核的求助。</p>
      ) : (
        <div className="workspace-grid">
          {items.map((item) => (
            <article className="workspace-card" key={item.request_id}>
              <span className="status-pill">{item.processing_status}</span>
              <h3>{item.intent}</h3>
              {item.question !== null && <p>{item.question}</p>}
              <p className="workspace-id">{item.request_id}</p>
              {item.human_review_reason !== null && (
                <p>{item.human_review_reason}</p>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
