import { BrandMark } from "../auth/ProductIntro";
import { ProfileMenu } from "./ProfileMenu";
import { PlatformIcon } from "./PlatformIcon";
import { getDisplayName, navigationItems, platformPaths, type PlatformPath } from "./platformData";

interface PlatformSidebarProps {
  account: string;
  isLoggingOut: boolean;
  onLogout: () => void;
  onNavigate: (path: PlatformPath) => void;
  pathname: PlatformPath;
}

export function PlatformSidebar({
  account,
  isLoggingOut,
  onLogout,
  onNavigate,
  pathname,
}: PlatformSidebarProps) {
  const displayName = getDisplayName(account);

  return (
    <aside className="platform-sidebar" aria-label="平台侧边栏">
      <a
        className="platform-brand"
        href={platformPaths.market}
        onClick={(event) => {
          event.preventDefault();
          onNavigate(platformPaths.market);
        }}
      >
        <BrandMark />
        <span>OrionAI</span>
      </a>

      <nav aria-label="主导航" className="platform-navigation">
        {navigationItems.map(({ path, label, icon }) => (
          <a
            aria-current={pathname === path ? "page" : undefined}
            className={`platform-navigation__item${pathname === path ? " is-active" : ""}`}
            href={path}
            key={path}
            onClick={(event) => {
              event.preventDefault();
              onNavigate(path);
            }}
          >
            <PlatformIcon name={icon} />
            <span>{label}</span>
          </a>
        ))}
      </nav>

      <div className="platform-sidebar__footer">
        <button
          className="workspace-link"
          onClick={() => onNavigate(platformPaths.workspace)}
          type="button"
        >
          <span className="workspace-link__avatar" aria-hidden="true">
            <PlatformIcon name="workspace" size={18} />
          </span>
          <span className="workspace-link__copy">
            <strong>个人空间</strong>
            <small>当前工作空间</small>
          </span>
        </button>
        <div className="sidebar-account">
          <span className="sidebar-account__identity" title={account}>
            <span className="sidebar-account__avatar" aria-hidden="true">
              {displayName.charAt(0).toUpperCase()}
            </span>
            <span className="sidebar-account__copy">
              <strong>{displayName}</strong>
              <small>已登录</small>
            </span>
          </span>
          <ProfileMenu
            account={account}
            isLoggingOut={isLoggingOut}
            onLogout={onLogout}
            onNavigate={onNavigate}
            triggerLabel="侧边栏用户菜单"
          />
        </div>
      </div>
    </aside>
  );
}
