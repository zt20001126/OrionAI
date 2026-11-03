import { useState, type ReactNode } from "react";

import "./platform.css";

import { ProfileMenu } from "./ProfileMenu";
import { PlatformSidebar } from "./PlatformSidebar";
import { MembershipEntry } from "../membership/MembershipEntry";
import { NotificationBell } from "../notifications/NotificationBell";
import { t } from "../../i18n/localeStore";
import {
  isMembershipCheckoutPath,
  isMembershipOrderDetailPath,
  isDigitalHumanPath,
  platformPaths,
  type PlatformRoute,
} from "./platformData";

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
  const pageTitle =
    pathname === platformPaths.market
      ? "技能市场"
      : pathname === platformPaths.mySkills
        ? "我的技能"
        : pathname === platformPaths.sessions
          ? "会话记录"
          : pathname === platformPaths.resume
            ? "简历助手"
            : pathname === platformPaths.reminders || pathname === platformPaths.reminderCreate
              ? pathname === platformPaths.reminderCreate
                ? "新建提醒"
                : "提醒助手"
              : pathname === platformPaths.settings
                ? "个人设置"
                : pathname === platformPaths.securitySettings
                  ? "安全设置"
                  : pathname === platformPaths.feedbackSettings
                    ? "问题反馈"
                    : pathname === platformPaths.chat ||
                        pathname.startsWith(`${platformPaths.chat}/`)
                      ? "对话助手"
                      : pathname === platformPaths.membership
                        ? "会员中心"
                        : isDigitalHumanPage
                          ? "数字人助手"
                          : isMembershipCheckoutPath(pathname)
                            ? "确认支付"
                            : pathname === platformPaths.membershipOrders
                              ? "我的订单"
                              : isMembershipOrderDetailPath(pathname)
                                ? "订单详情"
                                : "OrionAI";

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
        <header className="platform-topbar">
          <div className="platform-topbar__context">
            <strong>{t(pageTitle)}</strong>
          </div>
          <div className="platform-topbar__actions">
            <MembershipEntry onNavigate={onNavigate} />
            <NotificationBell account={isGuest ? null : account} isGuest={isGuest} />
            <ProfileMenu
              account={account}
              avatarUrl={avatarUrl}
              isLoggingOut={isLoggingOut}
              isGuest={isGuest}
              nickname={nickname}
              onLogout={onLogout}
              onNavigate={onNavigate}
              triggerLabel={t("更多用户选项")}
            />
          </div>
        </header>

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
