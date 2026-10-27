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
}

export function PlatformSidebar({
  account,
  avatarUrl,
  isLoggingOut,
  nickname,
  onLogout,
  onNavigate,
  pathname,
}: PlatformSidebarProps) {
  const activePath = pathname.startsWith(`${platformPaths.chat}`)
    ? platformPaths.mySkills
    : pathname;

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
            aria-current={activePath === path ? "page" : undefined}
            className={`platform-navigation__item${activePath === path ? " is-active" : ""}`}
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
          <ProfileMenu
            account={account}
            avatarUrl={avatarUrl}
            isLoggingOut={isLoggingOut}
            nickname={nickname}
            onLogout={onLogout}
            onNavigate={onNavigate}
            triggerLabel="侧边栏用户菜单"
            variant="sidebar"
          />
        </div>
      </div>
    </aside>
  );
}
