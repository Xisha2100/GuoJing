import { useCallback, useEffect, useState } from "react";

import { adminApi, isApiError } from "./api/client";
import type { AdminSession } from "./api/types";
import { LoginForm } from "./auth/LoginForm";
import { WorkspaceDashboard } from "./workspaces/WorkspaceDashboard";

export default function App() {
  const [session, setSession] = useState<AdminSession | null | undefined>(
    undefined,
  );
  const [startupError, setStartupError] = useState<string | null>(null);

  const returnToLogin = useCallback(() => setSession(null), []);

  useEffect(() => {
    adminApi
      .me()
      .then(setSession)
      .catch((caught: unknown) => {
        if (isApiError(caught, 401)) {
          setSession(null);
          return;
        }
        setStartupError(
          caught instanceof Error ? caught.message : "无法连接后端服务。",
        );
        setSession(null);
      });
  }, []);

  async function logout() {
    try {
      await adminApi.logout();
    } finally {
      setSession(null);
    }
  }

  if (session === undefined) {
    return (
      <main className="loading-screen">
        <div className="brand-mark" aria-hidden="true">
          老
        </div>
        <p>正在确认登录状态…</p>
      </main>
    );
  }

  if (session === null) {
    return (
      <>
        {startupError !== null && (
          <p className="global-notice notice notice-error" role="alert">
            {startupError}
          </p>
        )}
        <LoginForm
          onAuthenticated={(authenticated) => {
            setStartupError(null);
            setSession(authenticated);
          }}
        />
      </>
    );
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-lockup">
          <span className="brand-mark small" aria-hidden="true">
            老
          </span>
          <div>
            <strong>老牌子</strong>
            <span>教程管理台</span>
          </div>
        </div>
        <div className="account-actions">
          <span>管理员：{session.username}</span>
          <button
            className="text-button"
            type="button"
            onClick={() => void logout()}
          >
            退出登录
          </button>
        </div>
      </header>
      <main className="app-content">
        <WorkspaceDashboard onUnauthorized={returnToLogin} />
      </main>
    </div>
  );
}
