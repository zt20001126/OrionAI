import { useCallback, useEffect, useState } from "react";

import { AuthPage } from "../features/auth/AuthPage";
import { BrandMark, ProductIntro } from "../features/auth/ProductIntro";
import { PlatformLayout } from "../features/platform/PlatformLayout";
import { PlaceholderPage } from "../features/platform/PlaceholderPage";
import { SkillMarketPage } from "../features/platform/SkillMarketPage";
import {
  isPlatformPath,
  platformPaths,
  type PlatformPath,
} from "../features/platform/platformData";
import { getSession, logout } from "../features/auth/authApi";

type AppPath = PlatformPath | typeof platformPaths.login;

function getCurrentPath(): string {
  return window.location.pathname || "/";
}

export default function App() {
  const [account, setAccount] = useState<string | null>(null);
  const [pathname, setPathname] = useState(getCurrentPath);
  const [isRestoringSession, setIsRestoringSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const navigate = useCallback((path: AppPath, replace = false) => {
    const method = replace ? "replaceState" : "pushState";
    if (window.location.pathname !== path) {
      window.history[method]({}, "", path);
    }
    setPathname(path);
  }, []);

  useEffect(() => {
    function handlePopState() {
      setPathname(getCurrentPath());
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    let isActive = true;

    void getSession()
      .then((session) => {
        if (isActive) setAccount(session.authenticated ? session.account : null);
      })
      .catch(() => {
        if (isActive) {
          setSessionError("暂时无法连接认证服务，请检查后端、Redis 和数据库状态。");
        }
      })
      .finally(() => {
        if (isActive) setIsRestoringSession(false);
      });

    return () => {
      isActive = false;
    };
  }, []);

  useEffect(() => {
    if (isRestoringSession) return;

    let redirectPath: AppPath | null = null;
    if (account) {
      if (!isPlatformPath(pathname)) redirectPath = platformPaths.market;
    } else if (pathname !== platformPaths.login) {
      redirectPath = platformPaths.login;
    }

    if (redirectPath && window.location.pathname !== redirectPath) {
      window.history.replaceState({}, "", redirectPath);
    }
  }, [account, isRestoringSession, pathname]);

  async function handleLogout() {
    setLogoutError(null);
    setIsLoggingOut(true);
    try {
      await logout();
      setAccount(null);
      navigate(platformPaths.login, true);
    } catch {
      setLogoutError("退出失败，请检查连接后重试。");
    } finally {
      setIsLoggingOut(false);
    }
  }

  function handleAuthenticated(authenticatedAccount: string) {
    setSessionError(null);
    setLogoutError(null);
    setAccount(authenticatedAccount);
    navigate(platformPaths.market, true);
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

  if (!account) {
    return <AuthPage initialMessage={sessionError} onAuthenticated={handleAuthenticated} />;
  }

  const safePathname = isPlatformPath(pathname) ? pathname : platformPaths.market;
  const page =
    safePathname === platformPaths.market ? (
      <SkillMarketPage />
    ) : (
      <PlaceholderPage onNavigate={navigate} pathname={safePathname} />
    );

  return (
    <PlatformLayout
      account={account}
      isLoggingOut={isLoggingOut}
      logoutError={logoutError}
      onLogout={() => void handleLogout()}
      onNavigate={navigate}
      pathname={safePathname}
    >
      {page}
    </PlatformLayout>
  );
}
