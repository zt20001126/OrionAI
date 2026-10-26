import { useEffect, useState } from "react";

import { AuthPage } from "../features/auth/AuthPage";
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
      <main className="auth-shell">
        <section className="auth-card session-loading" aria-live="polite">
          <div className="brand-mark" aria-hidden="true">
            O
          </div>
          <p className="eyebrow">ORIONAI PLATFORM</p>
          <h1>正在恢复登录状态</h1>
        </section>
      </main>
    );
  }

  if (account) {
    return (
      <main className="auth-shell">
        <section className="auth-card signed-in-card" aria-labelledby="signed-in-title">
          <div className="brand-mark" aria-hidden="true">
            O
          </div>
          <p className="eyebrow">ORIONAI PLATFORM</p>
          <h1 id="signed-in-title">欢迎回来</h1>
          <p className="signed-in-account">{account}</p>
          <p className="signed-in-note">你的登录状态已通过安全 Cookie 恢复。</p>
          {logoutError && (
            <p className="form-message error-message" role="alert">
              {logoutError}
            </p>
          )}
          <button
            className="secondary-button logout-button"
            disabled={isLoggingOut}
            onClick={() => void handleLogout()}
          >
            {isLoggingOut ? "正在退出…" : "退出登录"}
          </button>
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
