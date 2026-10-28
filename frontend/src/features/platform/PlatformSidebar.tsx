import { BrandMark } from "../auth/ProductIntro";
import { ProfileMenu } from "./ProfileMenu";
import { PlatformIcon } from "./PlatformIcon";
import { navigationItems, platformPaths, type PlatformRoute } from "./platformData";

interface PlatformSidebarProps {
  account: string;
  avatarUrl?: string | null;
  isLoggingOut: boolean;
  nickname?: string | null;
  onLogout: () => void;
  onNavigate: (path: PlatformRoute) => void;
  pathname: PlatformRoute;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export function PlatformSidebar({
  account,
  avatarUrl,
  isLoggingOut,
  nickname,
  onLogout,
  onNavigate,
  pathname,
  collapsed,
  onToggleCollapsed,
}: PlatformSidebarProps) {
  const activePath = pathname.startsWith(`${platformPaths.chat}`)
    ? platformPaths.mySkills
    : pathname;

  return (
    <aside
      className={`platform-sidebar${collapsed ? " platform-sidebar--collapsed" : ""}`}
      aria-label="平台侧边栏"
    >
      <div className="platform-sidebar__top">
        <a
          aria-label="OrionAI 首页"
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
        <button
          aria-label={collapsed ? "展开导航栏" : "收起导航栏"}
          aria-expanded={!collapsed}
          className="platform-sidebar__toggle"
          onClick={onToggleCollapsed}
          title={collapsed ? "展开导航栏" : "收起导航栏"}
          type="button"
        >
          <PlatformIcon name={collapsed ? "expand" : "collapse"} size={18} />
        </button>
      </div>

      <nav aria-label="主导航" className="platform-navigation">
        {navigationItems.map(({ path, label, icon }) => (
          <a
            aria-current={activePath === path ? "page" : undefined}
            className={`platform-navigation__item${activePath === path ? " is-active" : ""}`}
            data-tooltip={label}
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
        <div className="sidebar-account">
          <ProfileMenu
            account={account}
            avatarUrl={avatarUrl}
            isLoggingOut={isLoggingOut}
            nickname={nickname}
            onLogout={onLogout}
            onNavigate={onNavigate}
            triggerLabel="侧边栏用户菜单"
            variant="sidebar"
            tooltipLabel={account}
            collapsed={collapsed}
          />
        </div>
      </div>
    </aside>
  );
}
