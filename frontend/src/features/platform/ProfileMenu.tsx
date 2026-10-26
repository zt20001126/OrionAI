import { useEffect, useId, useRef, useState } from "react";

import { getDisplayName, platformPaths, type PlatformPath } from "./platformData";
import { PlatformIcon } from "./PlatformIcon";

interface ProfileMenuProps {
  account: string;
  isLoggingOut: boolean;
  onLogout: () => void;
  onNavigate: (path: PlatformPath) => void;
  triggerLabel: string;
}

export function ProfileMenu({
  account,
  isLoggingOut,
  onLogout,
  onNavigate,
  triggerLabel,
}: ProfileMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const displayName = getDisplayName(account);

  useEffect(() => {
    if (!isOpen) return;

    function closeOnOutsideClick(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setIsOpen(false);
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setIsOpen(false);
    }

    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isOpen]);

  function openSettings() {
    setIsOpen(false);
    onNavigate(platformPaths.settings);
  }

  function logout() {
    setIsOpen(false);
    onLogout();
  }

  return (
    <div className="profile-menu" ref={rootRef}>
      <button
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label={triggerLabel}
        aria-controls={menuId}
        className="profile-menu__trigger"
        onClick={() => setIsOpen((open) => !open)}
        type="button"
      >
        <UserAvatar account={account} />
        <PlatformIcon name="chevron" size={15} />
      </button>

      {isOpen && (
        <div className="profile-menu__popover" id={menuId} role="menu">
          <div className="profile-menu__identity">
            <UserAvatar account={account} />
            <span>
              <strong>{displayName}</strong>
              <small title={account}>{account}</small>
            </span>
          </div>
          <div className="profile-menu__divider" />
          <button
            className="profile-menu__item"
            onClick={openSettings}
            role="menuitem"
            type="button"
          >
            <PlatformIcon name="settings" size={17} />
            个人设置
          </button>
          <button
            className="profile-menu__item profile-menu__item--danger"
            disabled={isLoggingOut}
            onClick={logout}
            role="menuitem"
            type="button"
          >
            <PlatformIcon name="logout" size={17} />
            {isLoggingOut ? "正在退出…" : "退出登录"}
          </button>
        </div>
      )}
    </div>
  );
}

export function UserAvatar({ account }: { account: string }) {
  const displayName = getDisplayName(account);
  return (
    <span aria-hidden="true" className="user-avatar">
      {displayName.charAt(0).toUpperCase()}
    </span>
  );
}
