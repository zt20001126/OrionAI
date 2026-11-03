import { useState, type ReactNode } from "react";

import { AmbientBackground } from "../../components/AmbientBackground";
import "./platform.css";

import { PlatformSidebar } from "./PlatformSidebar";
import { t } from "../../i18n/localeStore";
import { isDigitalHumanPath, platformPaths, type PlatformRoute } from "./platformData";

const SIDEBAR_COLLAPSED_STORAGE_KEY = "orionai:platform-sidebar-collapsed";

interface PlatformLayoutProps {
  account: string;
  avatarUrl?: string | null;
  children: ReactNode;
  isLoggingOut: boolean;
  isGuest?: boolean;
  nickname?: string | null;
  onLogout: () => void;
  onNavigate: (path: PlatformRoute) => void;
  pathname: PlatformRoute;
}

export function PlatformLayout({
  account,
  avatarUrl,
  children,
  isLoggingOut,
  isGuest = false,
  nickname,
  onLogout,
  onNavigate,
  pathname,
}: PlatformLayoutProps) {
  const isConversationPage =
    pathname === platformPaths.chat || pathname.startsWith(`${platformPaths.chat}/`);
  const isSessionsPage = pathname === platformPaths.sessions;
  const isResumePage = pathname === platformPaths.resume;
  const isDigitalHumanPage = isDigitalHumanPath(pathname);
  const [sidebarPreference, setSidebarPreference] = useState(readSidebarPreference);
  const sidebarCollapsed = sidebarPreference ?? isResumePage;

  function toggleSidebar() {
    const nextCollapsed = !sidebarCollapsed;
    setSidebarPreference(nextCollapsed);
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(nextCollapsed));
    } catch {
      // Keep the current session usable when browser storage is unavailable.
    }
  }

  return (
    <div
      className={`platform-shell${sidebarCollapsed ? " is-sidebar-collapsed" : ""}${isConversationPage ? " platform-shell--conversation" : ""}${isResumePage ? " platform-shell--resume" : ""}${isSessionsPage ? " platform-shell--sessions" : ""}${isDigitalHumanPage ? " platform-shell--digital-human" : ""}`}
    >
      <PlatformSidebar
        account={account}
        avatarUrl={avatarUrl}
        isLoggingOut={isLoggingOut}
        isGuest={isGuest}
        nickname={nickname}
        onLogout={onLogout}
        onNavigate={onNavigate}
        pathname={pathname}
        collapsed={sidebarCollapsed}
        onToggleCollapsed={toggleSidebar}
      />

      <div
        className={`platform-main${isConversationPage ? " platform-main--conversation" : ""}${isResumePage ? " platform-main--resume" : ""}${isSessionsPage ? " platform-main--sessions" : ""}${isDigitalHumanPage ? " platform-main--digital-human" : ""}`}
      >
        <AmbientBackground mode="app" />
        <main
          className={`platform-content${isConversationPage ? " platform-content--conversation" : ""}${isResumePage ? " platform-content--resume" : ""}${isSessionsPage ? " platform-content--sessions" : ""}${isDigitalHumanPage ? " platform-content--digital-human" : ""}`}
        >
          {children}
        </main>
        {!isConversationPage && !isResumePage && !isSessionsPage && !isDigitalHumanPage && (
          <footer className="platform-footer">{t("© OrionAI · 为智能体应用而构建")}</footer>
        )}
      </div>
    </div>
  );
}

function readSidebarPreference(): boolean | null {
  try {
    const preference = window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    return preference === "true" ? true : preference === "false" ? false : null;
  } catch {
    return null;
  }
}
