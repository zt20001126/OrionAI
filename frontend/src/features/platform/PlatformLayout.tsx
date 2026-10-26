import type { ReactNode } from "react";

import "./platform.css";

import { ProfileMenu } from "./ProfileMenu";
import { PlatformSidebar } from "./PlatformSidebar";
import { PlatformIcon } from "./PlatformIcon";
import type { PlatformPath } from "./platformData";

interface PlatformLayoutProps {
  account: string;
  children: ReactNode;
  isLoggingOut: boolean;
  logoutError: string | null;
  onLogout: () => void;
  onNavigate: (path: PlatformPath) => void;
  pathname: PlatformPath;
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
  return (
    <div className="platform-shell">
      <PlatformSidebar
        account={account}
        isLoggingOut={isLoggingOut}
        onLogout={onLogout}
        onNavigate={onNavigate}
        pathname={pathname}
      />

      <div className="platform-main">
        <header className="platform-topbar">
          <div className="platform-topbar__context">
            <span>工作空间</span>
            <PlatformIcon name="chevron" size={14} />
            <strong>{pathname === "/market" ? "技能市场" : "OrionAI"}</strong>
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

        <main className="platform-content">{children}</main>
        <footer className="platform-footer">© OrionAI · 为企业智能体应用而构建</footer>
      </div>
    </div>
  );
}
