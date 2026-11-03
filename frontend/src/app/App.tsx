import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";

import { ToastProvider, useToast } from "../components/ToastProvider";
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
import { ReminderPage } from "../features/reminders/ReminderPage";
import { MemoryTrainingPage } from "../features/memory-training/pages/MemoryTrainingPage";
import { MembershipStatusProvider } from "../features/membership/MembershipStatusContext";
import {
  getMembershipCheckoutPlanId,
  getMembershipCheckoutOrderId,
  getMembershipOrderId,
  getConversationId,
  getDigitalHumanConversationId,
  isConversationPath,
  isDigitalHumanPath,
  isMembershipCheckoutPath,
  isMembershipOrderDetailPath,
  isPlatformPath,
  isSettingsPath,
  platformPaths,
  type PlatformRoute,
} from "../features/platform/platformData";
import { getSession, logout, type AuthIdentity, type AuthMethod } from "../features/auth/authApi";
import { getUserProfile, type UserProfile } from "../features/platform/profileApi";
import { ensureWelcomeNotification } from "../features/notifications/notificationStorage";
import { LocaleProvider, useLocale } from "../i18n/LocaleProvider";
import { LanguageSwitcher } from "../i18n/LanguageSwitcher";
import { t } from "../i18n/localeStore";

type AppPath = PlatformRoute | typeof platformPaths.login;
type PopNavigationStage = "restoring" | "confirming" | "navigating";

const MembershipPage = lazy(() =>
  import("../features/membership/MembershipPage").then((module) => ({
    default: module.MembershipPage,
  })),
);
const DigitalHumanPage = lazy(() =>
  import("../features/digital-human/DigitalHumanPage").then((module) => ({
    default: module.DigitalHumanPage,
  })),
);
const MembershipCheckoutPage = lazy(() =>
  import("../features/membership/MembershipCheckoutPage").then((module) => ({
    default: module.MembershipCheckoutPage,
  })),
);
const MembershipOrdersPage = lazy(() =>
  import("../features/membership/MembershipOrdersPage").then((module) => ({
    default: module.MembershipOrdersPage,
  })),
);
const MembershipOrderDetailPage = lazy(() =>
  import("../features/membership/MembershipOrderDetailPage").then((module) => ({
    default: module.MembershipOrderDetailPage,
  })),
);

interface PendingPopNavigation {
  currentIndex: number;
  currentPath: string;
  targetIndex: number | null;
  targetPath: string;
  stage: PopNavigationStage;
  shouldPrompt: boolean;
}

const HISTORY_INDEX_KEY = "__orionHistoryIndex";

function getCurrentPath(): string {
  return window.location.pathname || "/";
}

export default function App() {
  return (
    <LocaleProvider>
      <ToastProvider>
        <AppContent />
      </ToastProvider>
    </LocaleProvider>
  );
}

function AppContent() {
  useLocale();
  const { confirm, showToast } = useToast();
  const [identity, setIdentity] = useState<AuthIdentity | null>(null);
  const account = identity?.account ?? null;
  const isGuest = identity?.is_guest ?? false;
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [pathname, setPathname] = useState(getCurrentPath);
  const [hasUnsavedSettings, setHasUnsavedSettings] = useState(false);
  const [hasUnsavedResume, setHasUnsavedResume] = useState(false);
  const [isRestoringSession, setIsRestoringSession] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [authSuccessMessage, setAuthSuccessMessage] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const guestRestrictedRedirect = getGuestRestrictedRedirect(pathname, isGuest);
  const historyIndexRef = useRef<number | null>(null);
  const pendingNavigationRef = useRef(false);
  const pendingPopNavigationRef = useRef<PendingPopNavigation | null>(null);
  const skipNextPopStateRef = useRef(false);

  useEffect(() => {
    const initialIndex = getHistoryIndex(window.history.state) ?? 0;
    historyIndexRef.current = initialIndex;
    window.history.replaceState(
      withHistoryIndex(window.history.state, initialIndex),
      "",
      window.location.href,
    );
  }, []);

  const navigate = useCallback(
    async (path: AppPath, replace = false) => {
      const shouldConfirmLeave =
        (isSettingsPath(pathname) && hasUnsavedSettings) ||
        (pathname === platformPaths.resume && hasUnsavedResume);
      if (path !== pathname && shouldConfirmLeave) {
        if (pendingNavigationRef.current) return;
        pendingNavigationRef.current = true;
        let confirmed: boolean;
        try {
          confirmed = await confirm(getLeaveConfirmation());
        } finally {
          pendingNavigationRef.current = false;
        }
        if (!confirmed) return;
      }

      const method = replace ? "replaceState" : "pushState";
      if (window.location.pathname !== path) {
        const currentIndex = historyIndexRef.current ?? 0;
        const nextIndex = replace ? currentIndex : currentIndex + 1;
        historyIndexRef.current = nextIndex;
        window.history[method](withHistoryIndex(window.history.state, nextIndex), "", path);
      }
      setPathname(path);
    },
    [confirm, hasUnsavedResume, hasUnsavedSettings, pathname],
  );

  useEffect(() => {
    function handlePopState(event: PopStateEvent) {
      const nextPath = getCurrentPath();
      const nextIndex = getHistoryIndex(event.state);

      const pendingPopNavigation = pendingPopNavigationRef.current;
      if (pendingPopNavigation) {
        if (pendingPopNavigation.stage === "navigating") {
          if (nextIndex === null || nextIndex === pendingPopNavigation.targetIndex) {
            historyIndexRef.current = nextIndex ?? pendingPopNavigation.targetIndex;
            setPathname(nextPath);
            pendingPopNavigationRef.current = null;
            pendingNavigationRef.current = false;
          }
          return;
        }

        if (pendingPopNavigation.stage === "restoring") {
          if (nextIndex === pendingPopNavigation.currentIndex) {
            historyIndexRef.current = nextIndex;
            setPathname(pendingPopNavigation.currentPath);
            pendingPopNavigation.stage = "confirming";
            if (pendingPopNavigation.shouldPrompt) {
              pendingPopNavigation.shouldPrompt = false;
              void confirm(getLeaveConfirmation()).then((confirmed) => {
                if (pendingPopNavigationRef.current !== pendingPopNavigation) return;
                if (!confirmed) {
                  pendingPopNavigationRef.current = null;
                  pendingNavigationRef.current = false;
                  return;
                }

                pendingPopNavigation.stage = "navigating";
                if (pendingPopNavigation.targetIndex === null) {
                  const currentIndex = historyIndexRef.current ?? 0;
                  historyIndexRef.current = currentIndex;
                  window.history.replaceState(
                    withHistoryIndex(window.history.state, currentIndex),
                    "",
                    pendingPopNavigation.targetPath,
                  );
                  setPathname(pendingPopNavigation.targetPath);
                  pendingPopNavigationRef.current = null;
                  pendingNavigationRef.current = false;
                  return;
                }

                window.history.go(
                  pendingPopNavigation.targetIndex - pendingPopNavigation.currentIndex,
                );
              });
            }
          } else if (nextIndex !== null) {
            window.history.go(pendingPopNavigation.currentIndex - nextIndex);
          }
          return;
        }

        if (nextIndex !== null && nextIndex !== pendingPopNavigation.currentIndex) {
          pendingPopNavigation.stage = "restoring";
          pendingPopNavigation.shouldPrompt = false;
          window.history.go(pendingPopNavigation.currentIndex - nextIndex);
        }
        return;
      }

      if (skipNextPopStateRef.current) {
        skipNextPopStateRef.current = false;
        if (nextIndex !== null) historyIndexRef.current = nextIndex;
        setPathname(nextPath);
        return;
      }
      if (pendingNavigationRef.current) {
        const currentIndex = historyIndexRef.current;
        if (nextIndex !== null && currentIndex !== null && nextIndex !== currentIndex) {
          skipNextPopStateRef.current = true;
          window.history.go(currentIndex - nextIndex);
        }
        return;
      }
      const shouldConfirmLeave =
        (isSettingsPath(pathname) && hasUnsavedSettings) ||
        (pathname === platformPaths.resume && hasUnsavedResume);
      if (nextPath !== pathname && shouldConfirmLeave) {
        const currentIndex = historyIndexRef.current ?? 0;
        if (nextIndex === null) {
          window.history.pushState(
            withHistoryIndex(window.history.state, currentIndex),
            "",
            pathname,
          );
          pendingNavigationRef.current = true;
          void confirm(getLeaveConfirmation())
            .then((confirmed) => {
              if (confirmed) {
                window.history.replaceState(
                  withHistoryIndex(window.history.state, currentIndex),
                  "",
                  nextPath,
                );
                setPathname(nextPath);
              }
            })
            .finally(() => {
              pendingNavigationRef.current = false;
            });
          return;
        }

        const pendingNavigation: PendingPopNavigation = {
          currentIndex,
          currentPath: pathname,
          targetIndex: nextIndex,
          targetPath: nextPath,
          stage: "restoring",
          shouldPrompt: true,
        };
        pendingPopNavigationRef.current = pendingNavigation;
        pendingNavigationRef.current = true;
        window.history.go(currentIndex - nextIndex);
        return;
      }
      if (nextIndex !== null) historyIndexRef.current = nextIndex;
      setPathname(nextPath);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [confirm, hasUnsavedResume, hasUnsavedSettings, pathname]);

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
    if (!identity) return;

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
  }, [identity]);

  useEffect(() => {
    let isActive = true;

    void getSession()
      .then((session) => {
        if (isActive) {
          setIdentity(
            session.authenticated
              ? { account: session.account, is_guest: session.is_guest ?? false }
              : null,
          );
        }
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
    if (identity) {
      if (guestRestrictedRedirect) {
        redirectPath = guestRestrictedRedirect;
      } else if (!isPlatformPath(pathname)) {
        redirectPath = platformPaths.market;
      }
    } else if (pathname !== platformPaths.login) {
      redirectPath = platformPaths.login;
    }

    if (redirectPath && window.location.pathname !== redirectPath) {
      const currentIndex = historyIndexRef.current ?? 0;
      historyIndexRef.current = currentIndex;
      window.history.replaceState(
        withHistoryIndex(window.history.state, currentIndex),
        "",
        redirectPath,
      );
    }
  }, [guestRestrictedRedirect, identity, isRestoringSession, pathname]);

  async function handleLogout() {
    setIsLoggingOut(true);
    try {
      await logout();
      setHasUnsavedSettings(false);
      setIdentity(null);
      setUserProfile(null);
      const currentIndex = historyIndexRef.current ?? 0;
      window.history.replaceState(
        withHistoryIndex(window.history.state, currentIndex),
        "",
        platformPaths.login,
      );
      setPathname(platformPaths.login);
    } catch {
      showToast("error", t("退出失败，请检查连接后重试。"));
    } finally {
      setIsLoggingOut(false);
    }
  }

  async function handleAuthenticated(authenticatedIdentity: AuthIdentity, method: AuthMethod) {
    if (method === "register" && !authenticatedIdentity.is_guest && authenticatedIdentity.account) {
      await ensureWelcomeNotification(authenticatedIdentity.account);
    }
    if (method === "login" && !authenticatedIdentity.is_guest) {
      showToast("info", t("欢迎回来，祝你使用愉快！"));
    }

    setSessionError(null);
    setAuthSuccessMessage(null);
    setHasUnsavedSettings(false);
    setUserProfile(null);
    setIdentity(authenticatedIdentity);
    navigate(platformPaths.market, true);
  }

  function handlePasswordChanged(message: string) {
    setUserProfile(null);
    setHasUnsavedSettings(false);
    setSessionError(null);
    setAuthSuccessMessage(message);
    setIdentity(null);
    const currentIndex = historyIndexRef.current ?? 0;
    window.history.replaceState(
      withHistoryIndex(window.history.state, currentIndex),
      "",
      platformPaths.login,
    );
    setPathname(platformPaths.login);
  }

  if (isRestoringSession) {
    return (
      <main className="auth-layout">
        <ProductIntro />
        <section className="auth-panel">
          <LanguageSwitcher className="language-switcher--auth" />
          <section className="auth-card status-card" aria-live="polite">
            <div className="auth-card-brand">
              <BrandMark />
              <span>OrionAI</span>
            </div>
            <span className="status-spinner" aria-hidden="true" />
            <h1>{t("正在恢复登录状态")}</h1>
            <p>{t("请稍候，我们正在确认你的安全会话。")}</p>
          </section>
        </section>
      </main>
    );
  }

  if (!identity) {
    return (
      <AuthPage
        initialMessage={sessionError ? t(sessionError) : null}
        initialSuccessMessage={authSuccessMessage}
        onAuthenticated={handleAuthenticated}
      />
    );
  }

  const guestSafePathname = guestRestrictedRedirect ?? pathname;
  const safePathname: PlatformRoute = isPlatformPath(guestSafePathname)
    ? guestSafePathname
    : platformPaths.market;
  const conversationId = getConversationId(safePathname);
  const digitalHumanConversationId = getDigitalHumanConversationId(safePathname);
  const page = (() => {
    if (safePathname === platformPaths.market) return <SkillMarketPage onNavigate={navigate} />;
    if (safePathname === platformPaths.mySkills) return <MySkillsPage onNavigate={navigate} />;
    if (safePathname === platformPaths.resume) {
      return <ResumePage onDirtyChange={setHasUnsavedResume} onNavigate={navigate} />;
    }
    if (safePathname === platformPaths.reminders || safePathname === platformPaths.reminderCreate) {
      return (
        <ReminderPage
          isGuest={isGuest}
          key={safePathname}
          mode={safePathname === platformPaths.reminderCreate ? "create" : "list"}
          onNavigate={navigate}
        />
      );
    }
    if (safePathname === platformPaths.memoryTraining) {
      return <MemoryTrainingPage onNavigate={navigate} />;
    }
    if (isDigitalHumanPath(safePathname)) {
      return <DigitalHumanPage conversationId={digitalHumanConversationId} onNavigate={navigate} />;
    }
    if (safePathname === platformPaths.membership) {
      return <MembershipPage isGuest={isGuest} onNavigate={navigate} />;
    }
    if (isMembershipCheckoutPath(safePathname)) {
      return (
        <MembershipCheckoutPage
          isGuest={isGuest}
          orderId={getMembershipCheckoutOrderId(safePathname)}
          planId={getMembershipCheckoutPlanId(safePathname) ?? ""}
          onNavigate={navigate}
        />
      );
    }
    if (safePathname === platformPaths.membershipOrders) {
      return <MembershipOrdersPage onNavigate={navigate} />;
    }
    if (isMembershipOrderDetailPath(safePathname)) {
      return (
        <MembershipOrderDetailPage
          onNavigate={navigate}
          orderId={getMembershipOrderId(safePathname) ?? ""}
        />
      );
    }
    if (safePathname === platformPaths.sessions) return <SessionsPage onNavigate={navigate} />;
    if (
      safePathname === platformPaths.settings ||
      safePathname === platformPaths.securitySettings ||
      safePathname === platformPaths.feedbackSettings
    ) {
      return (
        <SettingsPage
          account={account ?? ""}
          isGuest={isGuest}
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
    <MembershipStatusProvider isGuest={isGuest}>
      <PlatformLayout
        account={account ?? t("访客用户")}
        avatarUrl={userProfile?.avatar_url}
        isGuest={isGuest}
        isLoggingOut={isLoggingOut}
        nickname={userProfile?.nickname}
        onLogout={() => void handleLogout()}
        onNavigate={navigate}
        pathname={safePathname}
      >
        <Suspense
          fallback={
            <div className="membership-route-loading" role="status">
              {t("正在打开页面…")}
            </div>
          }
        >
          {page}
        </Suspense>
      </PlatformLayout>
    </MembershipStatusProvider>
  );
}

function getLeaveConfirmation() {
  return {
    title: t("离开当前页面？"),
    description: t("当前修改尚未保存，离开后更改将丢失。"),
    cancelLabel: t("继续编辑"),
    confirmLabel: t("放弃修改并离开"),
    tone: "warning" as const,
  };
}

function getGuestRestrictedRedirect(pathname: string, isGuest: boolean): AppPath | null {
  if (!isGuest) return null;
  if (pathname === platformPaths.securitySettings) return platformPaths.settings;
  if (pathname === platformPaths.reminderCreate) return platformPaths.reminders;
  return null;
}

function getHistoryIndex(state: unknown): number | null {
  if (!state || typeof state !== "object" || !(HISTORY_INDEX_KEY in state)) return null;
  const index = (state as Record<string, unknown>)[HISTORY_INDEX_KEY];
  return typeof index === "number" && Number.isInteger(index) ? index : null;
}

function withHistoryIndex(state: unknown, index: number): Record<string, unknown> {
  const safeState =
    state && typeof state === "object" && !Array.isArray(state)
      ? (state as Record<string, unknown>)
      : {};
  return { ...safeState, [HISTORY_INDEX_KEY]: index };
}
