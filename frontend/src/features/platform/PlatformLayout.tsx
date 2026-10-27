import type { ReactNode } from "react";

import "./platform.css";

import { ProfileMenu } from "./ProfileMenu";
import { PlatformSidebar } from "./PlatformSidebar";
import { PlatformIcon } from "./PlatformIcon";
import { platformPaths, type PlatformRoute } from "./platformData";

interface PlatformLayoutProps {
  account: string;
  avatarUrl?: string | null;
  children: ReactNode;
  isLoggingOut: boolean;
  logoutError: string | null;
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
  logoutError,
  nickname,
  onLogout,
  onNavigate,
  pathname,
}: PlatformLayoutProps) {
  const isConversationPage =
    pathname === platformPaths.chat || pathname.startsWith(`${platformPaths.chat}/`);
  const isResumePage = pathname === platformPaths.resume;
  const pageTitle =
    pathname === platformPaths.market
      ? "技能市场"
      : pathname === platformPaths.mySkills
        ? "我的技能"
        : pathname === platformPaths.sessions
          ? "会话记录"
          : pathname === platformPaths.resume
            ? "简历助手"
            : pathname === platformPaths.settings
              ? "个人设置"
              : pathname === platformPaths.securitySettings
                ? "安全设置"
                : pathname === platformPaths.chat || pathname.startsWith(`${platformPaths.chat}/`)
                  ? "通用对话助手"
                  : "OrionAI";

  return (
    <div
      className={`platform-shell${isConversationPage ? " platform-shell--conversation" : ""}${isResumePage ? " platform-shell--resume" : ""}`}
    >
      <PlatformSidebar
        account={account}
        avatarUrl={avatarUrl}
        isLoggingOut={isLoggingOut}
        nickname={nickname}
        onLogout={onLogout}
        onNavigate={onNavigate}
        pathname={pathname}
      />

      <div
        className={`platform-main${isConversationPage ? " platform-main--conversation" : ""}${isResumePage ? " platform-main--resume" : ""}`}
      >
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
              avatarUrl={avatarUrl}
              isLoggingOut={isLoggingOut}
              nickname={nickname}
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
          className={`platform-content${isConversationPage ? " platform-content--conversation" : ""}${isResumePage ? " platform-content--resume" : ""}`}
        >
          {children}
        </main>
        {!isConversationPage && !isResumePage && (
          <footer className="platform-footer">© OrionAI · 为企业智能体应用而构建</footer>
        )}
      </div>
    </div>
  );
}
