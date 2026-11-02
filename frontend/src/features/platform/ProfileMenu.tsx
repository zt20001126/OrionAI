import { useCallback, useEffect, useId, useRef, useState } from "react";

import { getDisplayName, platformPaths, type PlatformPath } from "./platformData";
import { PlatformIcon } from "./PlatformIcon";
import { FeedbackDialog } from "../feedback/FeedbackDialog";
import { LanguageSwitcher } from "../../i18n/LanguageSwitcher";
import { t } from "../../i18n/localeStore";

interface ProfileMenuProps {
  account: string;
  avatarUrl?: string | null;
  isLoggingOut: boolean;
  isGuest?: boolean;
  nickname?: string | null;
  onLogout: () => void;
  onNavigate: (path: PlatformPath) => void;
  triggerLabel: string;
  variant?: "default" | "sidebar";
  tooltipLabel?: string;
  collapsed?: boolean;
}

export function ProfileMenu({
  account,
  avatarUrl,
  isLoggingOut,
  isGuest = false,
  nickname,
  onLogout,
  onNavigate,
  triggerLabel,
  variant = "default",
  tooltipLabel,
  collapsed = false,
}: ProfileMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isPresent, setIsPresent] = useState(false);
  const [isFeedbackOpen, setIsFeedbackOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const displayName = nickname?.trim() || (isGuest ? t("访客用户") : getDisplayName(account));

  const closeMenu = useCallback(() => {
    setIsOpen(false);
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setIsPresent(false);
    }
  }, []);

  const openMenu = useCallback(() => {
    setIsPresent(true);
    setIsOpen(true);
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    function closeOnOutsideClick(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) closeMenu();
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        closeMenu();
        triggerRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [closeMenu, isOpen]);

  function openSettings() {
    closeMenu();
    onNavigate(platformPaths.settings);
  }

  function openSecuritySettings() {
    closeMenu();
    onNavigate(platformPaths.securitySettings);
  }

  function openFeedback() {
    closeMenu();
    setIsFeedbackOpen(true);
  }

  function logout() {
    closeMenu();
    onLogout();
  }

  return (
    <div
      className={`profile-menu${variant === "sidebar" ? " profile-menu--sidebar" : ""}`}
      ref={rootRef}
    >
      <button
        aria-expanded={isOpen}
        aria-haspopup="menu"
        aria-label={t(triggerLabel)}
        aria-controls={isPresent ? menuId : undefined}
        className={`profile-menu__trigger${variant === "sidebar" ? " profile-menu__trigger--sidebar" : ""}`}
        data-tooltip={tooltipLabel}
        onClick={isOpen ? closeMenu : openMenu}
        ref={triggerRef}
        title={variant === "sidebar" && !collapsed ? (isGuest ? t("访客用户") : account) : undefined}
        type="button"
      >
        <UserAvatar account={account} avatarUrl={avatarUrl} key={avatarUrl || "default-avatar"} />
        {variant === "sidebar" && (
          <span className="profile-menu__trigger-copy">
            <strong>{displayName}</strong>
            <small>{isGuest ? t("访客体验") : t("已登录")}</small>
          </span>
        )}
        <PlatformIcon name="chevron" size={15} />
      </button>

      {isPresent && (
        <div
          aria-hidden={!isOpen}
          className={`profile-menu__popover${isOpen ? "" : " is-closing"}`}
          id={menuId}
          inert={!isOpen}
          onAnimationEnd={(event) => {
            if (!isOpen && event.target === event.currentTarget) setIsPresent(false);
          }}
          role="menu"
        >
          <div className="profile-menu__identity">
            <UserAvatar
              account={account}
              avatarUrl={avatarUrl}
              key={avatarUrl || "default-avatar"}
            />
            <span>
              <strong>{displayName}</strong>
              <small title={account}>{isGuest ? t("访客账号 · 默认有效 7 天") : account}</small>
            </span>
          </div>
          <div className="profile-menu__divider" />
          <LanguageSwitcher
            icon={<PlatformIcon name="language" size={17} />}
            variant="menu-item"
          />
          <button
            className="profile-menu__item"
            onClick={openSettings}
            role="menuitem"
            type="button"
          >
            <PlatformIcon name="settings" size={17} />
            {t("个人设置")}
          </button>
          <button
            className="profile-menu__item"
            onClick={openSecuritySettings}
            role="menuitem"
            type="button"
          >
            <PlatformIcon name="settings" size={17} />
            {t("安全设置")}
          </button>
          <button
            className="profile-menu__item"
            onClick={openFeedback}
            role="menuitem"
            type="button"
          >
            <PlatformIcon name="message" size={17} />
            {t("问题反馈")}
          </button>
          <button
            className="profile-menu__item profile-menu__item--danger"
            disabled={isLoggingOut}
            onClick={logout}
            role="menuitem"
            type="button"
          >
            <PlatformIcon name="logout" size={17} />
            {isLoggingOut ? t("正在退出…") : t("退出登录")}
          </button>
        </div>
      )}
      {isFeedbackOpen && (
        <FeedbackDialog
          onClose={() => setIsFeedbackOpen(false)}
          restoreFocus={() => triggerRef.current?.focus()}
        />
      )}
    </div>
  );
}

export function UserAvatar({ account, avatarUrl }: { account: string; avatarUrl?: string | null }) {
  const [imageFailed, setImageFailed] = useState(false);
  const displayName = getDisplayName(account);

  return (
    <span aria-hidden="true" className="user-avatar">
      {!imageFailed ? (
        <img
          alt=""
          onError={() => setImageFailed(true)}
          src={avatarUrl || "/avatar/default_avatar.png"}
        />
      ) : (
        displayName.charAt(0).toUpperCase()
      )}
    </span>
  );
}
