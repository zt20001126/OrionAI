import { useCallback, useEffect, useState } from "react";

import { ToastProvider } from "../components/ToastProvider";
import { AuthPage } from "../features/auth/AuthPage";
import { BrandMark, ProductIntro } from "../features/auth/ProductIntro";
import { PlatformLayout } from "../features/platform/PlatformLayout";
import { PlaceholderPage } from "../features/platform/PlaceholderPage";
import { SettingsPage } from "../features/platform/SettingsPage";
import { SkillMarketPage } from "../features/platform/SkillMarketPage";
import { ConversationPage } from "../features/conversations/ConversationPage";
import { SessionsPage } from "../features/conversations/SessionsPage";
import { MySkillsPage } from "../features/skills/MySkillsPage";
import { ResumePage } from "../features/resume/ResumePage";
import {
  getConversationId,
  isConversationPath,
  isPlatformPath,
  platformPaths,
  type PlatformRoute,
} from "../features/platform/platformData";
import { getSession, logout } from "../features/auth/authApi";
import { getUserProfile, type UserProfile } from "../features/platform/profileApi";

type AppPath = PlatformRoute | typeof platformPaths.login;

function getCurrentPath(): string {
  return window.location.pathname || "/";
}

export default function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  );
}

function AppContent() {
  const [account, setAccount] = useState<string | null>(null);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [pathname, setPathname] = useState(getCurrentPath);
  const [hasUnsavedSettings, setHasUnsavedSettings] = useState(false);
  const [hasUnsavedResume, setHasUnsavedResume] = useState(false);
  const [isRestoringSession, setIsRestoringSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [authSuccessMessage, setAuthSuccessMessage] = useState<string | null>(null);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const navigate = useCallback(
    (path: AppPath, replace = false) => {
      const isSettingsPath =
        pathname === platformPaths.settings || pathname === platformPaths.securitySettings;
      const shouldConfirmLeave =
        (isSettingsPath && hasUnsavedSettings) ||
        (pathname === platformPaths.resume && hasUnsavedResume);
      if (
        path !== pathname &&
        shouldConfirmLeave &&
        !window.confirm(
          pathname === platformPaths.resume
            ? "简历有未保存的修改，确定离开吗？"
            : "当前设置有尚未保存的更改，确定离开吗？",
        )
      ) {
        return;
      }

      const method = replace ? "replaceState" : "pushState";
      if (window.location.pathname !== path) {
        window.history[method]({}, "", path);
      }
      setPathname(path);
    },
    [hasUnsavedResume, hasUnsavedSettings, pathname],
  );

  useEffect(() => {
    function handlePopState() {
      const nextPath = getCurrentPath();
      const isSettingsPath =
        pathname === platformPaths.settings || pathname === platformPaths.securitySettings;
      const shouldConfirmLeave =
        (isSettingsPath && hasUnsavedSettings) ||
        (pathname === platformPaths.resume && hasUnsavedResume);
      if (
        nextPath !== pathname &&
        shouldConfirmLeave &&
        !window.confirm(
          pathname === platformPaths.resume
            ? "简历有未保存的修改，确定离开吗？"
            : "当前设置有尚未保存的更改，确定离开吗？",
        )
      ) {
        window.history.pushState({}, "", pathname);
        return;
      }
      setPathname(nextPath);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [hasUnsavedResume, hasUnsavedSettings, pathname]);

  useEffect(() => {
    if (!hasUnsavedSettings && !hasUnsavedResume) return;
    function warnBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [hasUnsavedResume, hasUnsavedSettings]);

  useEffect(() => {
    if (!account) return;

    let isActive = true;
    void getUserProfile()
      .then((profile) => {
        if (isActive) setUserProfile(profile);
      })
      .catch(() => {
        if (isActive) setUserProfile(null);
      });

    return () => {
      isActive = false;
    };
  }, [account]);

  useEffect(() => {
    let isActive = true;

    void getSession()
      .then((session) => {
        if (isActive) setAccount(session.authenticated ? session.account : null);
      })
      .catch(() => {
        if (isActive) {
          setSessionError("认证服务暂时无法连接，请稍后重试。");
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
      setHasUnsavedSettings(false);
      setAccount(null);
      setUserProfile(null);
      window.history.replaceState({}, "", platformPaths.login);
      setPathname(platformPaths.login);
    } catch {
      setLogoutError("退出失败，请检查连接后重试。");
    } finally {
      setIsLoggingOut(false);
    }
  }

  function handleAuthenticated(authenticatedAccount: string) {
    setSessionError(null);
    setAuthSuccessMessage(null);
    setLogoutError(null);
    setHasUnsavedSettings(false);
    setUserProfile(null);
    setAccount(authenticatedAccount);
    navigate(platformPaths.market, true);
  }

  function handlePasswordChanged(message: string) {
    setUserProfile(null);
    setHasUnsavedSettings(false);
    setSessionError(null);
    setAuthSuccessMessage(message);
    setAccount(null);
    window.history.replaceState({}, "", platformPaths.login);
    setPathname(platformPaths.login);
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
    return (
      <AuthPage
        initialMessage={sessionError}
        initialSuccessMessage={authSuccessMessage}
        onAuthenticated={handleAuthenticated}
      />
    );
  }

  const safePathname: PlatformRoute = isPlatformPath(pathname) ? pathname : platformPaths.market;
  const conversationId = getConversationId(safePathname);
  const page = (() => {
    if (safePathname === platformPaths.market) return <SkillMarketPage />;
    if (safePathname === platformPaths.mySkills) return <MySkillsPage onNavigate={navigate} />;
    if (safePathname === platformPaths.resume) {
      return <ResumePage onDirtyChange={setHasUnsavedResume} onNavigate={navigate} />;
    }
    if (safePathname === platformPaths.sessions) return <SessionsPage onNavigate={navigate} />;
    if (
      safePathname === platformPaths.settings ||
      safePathname === platformPaths.securitySettings
    ) {
      return (
        <SettingsPage
          account={account}
          onDirtyChange={setHasUnsavedSettings}
          onNavigate={navigate}
          onPasswordChanged={handlePasswordChanged}
          onProfileUpdated={setUserProfile}
          pathname={safePathname}
        />
      );
    }
    if (isConversationPath(safePathname)) {
      return <ConversationPage conversationId={conversationId} onNavigate={navigate} />;
    }
    return <PlaceholderPage onNavigate={navigate} pathname={safePathname} />;
  })();

  return (
    <PlatformLayout
      account={account}
      avatarUrl={userProfile?.avatar_url}
      isLoggingOut={isLoggingOut}
      logoutError={logoutError}
      nickname={userProfile?.nickname}
      onLogout={() => void handleLogout()}
      onNavigate={navigate}
      pathname={safePathname}
    >
      {page}
    </PlatformLayout>
  );
}
