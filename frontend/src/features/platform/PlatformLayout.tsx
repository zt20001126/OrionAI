import type { ReactNode } from "react";

import "./platform.css";

import { ProfileMenu } from "./ProfileMenu";
import { PlatformSidebar } from "./PlatformSidebar";
import { PlatformIcon } from "./PlatformIcon";
import { platformPaths, type PlatformRoute } from "./platformData";

interface PlatformLayoutProps {
  account: string;
  children: ReactNode;
  isLoggingOut: boolean;
  logoutError: string | null;
  onLogout: () => void;
  onNavigate: (path: PlatformRoute) => void;
  pathname: PlatformRoute;
}

export function PlatformLayout({
  account,
  children,
  isLoggingOut,
  logoutError,
  onLogout,
  onNavigate,
  pathname,
}: PlatformLayoutProps) {
  const isConversationPage =
    pathname === platformPaths.chat || pathname.startsWith(`${platformPaths.chat}/`);
  const pageTitle =
    pathname === platformPaths.market
      ? "技能市场"
      : pathname === platformPaths.mySkills
        ? "我的技能"
        : pathname === platformPaths.sessions
          ? "会话记录"
        : pathname === platformPaths.settings
          ? "个人设置"
          : pathname === platformPaths.chat || pathname.startsWith(`${platformPaths.chat}/`)
            ? "通用对话助手"
            : "OrionAI";

  return (
    <div className={`platform-shell${isConversationPage ? " platform-shell--conversation" : ""}`}>
      <PlatformSidebar
        account={account}
        isLoggingOut={isLoggingOut}
        onLogout={onLogout}
        onNavigate={onNavigate}
        pathname={pathname}
      />

      <div className={`platform-main${isConversationPage ? " platform-main--conversation" : ""}`}>
        <header className="platform-topbar">
          <div className="platform-topbar__context">
            <span>工作空间</span>
            <PlatformIcon name="chevron" size={14} />
            <strong>{pageTitle}</strong>
          </div>
          <div className="platform-topbar__actions">
            <button aria-label="通知" className="notification-button" type="button">
              <PlatformIcon name="bell" />
              <span aria-hidden="true" />
            </button>
            <ProfileMenu
              account={account}
              isLoggingOut={isLoggingOut}
              onLogout={onLogout}
              onNavigate={onNavigate}
              triggerLabel="更多用户选项"
            />
          </div>
        </header>

        {logoutError && (
          <div className="platform-global-error" role="alert">
            {logoutError}
          </div>
        )}

        <main
          className={`platform-content${isConversationPage ? " platform-content--conversation" : ""}`}
        >
          {children}
        </main>
        {!isConversationPage && (
          <footer className="platform-footer">© OrionAI · 为企业智能体应用而构建</footer>
        )}
      </div>
    </div>
  );
}
