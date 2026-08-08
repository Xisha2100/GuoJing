import { useState, type FormEvent } from "react";

import { adminApi } from "../api/client";
import type { AdminSession } from "../api/types";

interface LoginFormProps {
  onAuthenticated: (session: AdminSession) => void;
}

export function LoginForm({ onAuthenticated }: LoginFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const session = await adminApi.login(username, password);
      setPassword("");
      onAuthenticated(session);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "登录失败，请稍后重试。",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card" aria-labelledby="login-title">
        <div className="brand-mark" aria-hidden="true">
          老
        </div>
        <p className="eyebrow">老牌子教程管理</p>
        <h1 id="login-title">管理员登录</h1>
        <p className="muted">登录后可以录入、校验和提升手机操作教程。</p>
        <form onSubmit={(event) => void submit(event)}>
          <label htmlFor="username">用户名</label>
          <input
            id="username"
            name="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
          <label htmlFor="password">密码</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {error !== null && (
            <p className="notice notice-error" role="alert">
              {error}
            </p>
          )}
          <button
            className="primary-button full-width"
            type="submit"
            disabled={submitting}
          >
            {submitting ? "正在登录…" : "登录"}
          </button>
        </form>
      </section>
    </main>
  );
}
