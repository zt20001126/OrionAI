import { useEffect, useState } from "react";

import { AuthPage } from "../features/auth/AuthPage";
import { BrandMark, ProductIntro } from "../features/auth/ProductIntro";
import { getSession, logout } from "../features/auth/authApi";

export default function App() {
  const [account, setAccount] = useState<string | null>(null);
  const [isRestoringSession, setIsRestoringSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  useEffect(() => {
    let isActive = true;

    void getSession()
      .then((session) => {
        if (isActive) {
          setAccount(session.authenticated ? session.account : null);
        }
      })
      .catch(() => {
        if (isActive) {
          setSessionError("暂时无法连接认证服务，请检查后端、Redis 和数据库状态。");
        }
      })
      .finally(() => {
        if (isActive) {
          setIsRestoringSession(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, []);

  async function handleLogout() {
    setLogoutError(null);
    setIsLoggingOut(true);
    try {
      await logout();
      setAccount(null);
    } catch {
      setLogoutError("退出失败，请检查连接后重试。");
    } finally {
      setIsLoggingOut(false);
    }
  }

  if (isRestoringSession) {
    return (
      <main className="auth-layout">
        <ProductIntro />
        <section className="auth-panel">
          <section className="auth-card status-card" aria-live="polite">
            <div className="auth-card-brand">
              <BrandMark />
              <span>OrionAI</span>
            </div>
            <span className="status-spinner" aria-hidden="true" />
            <h1>正在恢复登录状态</h1>
            <p>请稍候，我们正在确认你的安全会话。</p>
          </section>
        </section>
      </main>
    );
  }

  if (account) {
    return (
      <main className="auth-layout">
        <ProductIntro />
        <section className="auth-panel">
          <section
            className="auth-card status-card signed-in-card"
            aria-labelledby="signed-in-title"
          >
            <div className="auth-card-brand">
              <BrandMark />
              <span>OrionAI</span>
            </div>
            <div className="signed-in-check" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="m6 12.5 4 4L18 8" />
              </svg>
            </div>
            <p className="status-eyebrow">ACCOUNT</p>
            <h1 id="signed-in-title">欢迎回来</h1>
            <p className="signed-in-account">{account}</p>
            <p className="status-card-copy">你的登录状态已通过安全 Cookie 恢复。</p>
            {logoutError && (
              <p className="form-message error-message" role="alert">
                {logoutError}
              </p>
            )}
            <button
              className="button button--secondary logout-button"
              disabled={isLoggingOut}
              onClick={() => void handleLogout()}
            >
              {isLoggingOut ? "正在退出…" : "退出登录"}
            </button>
          </section>
        </section>
      </main>
    );
  }

  return (
    <AuthPage
      initialMessage={sessionError}
      onAuthenticated={(authenticatedAccount) => {
        setSessionError(null);
        setAccount(authenticatedAccount);
      }}
    />
  );
}
