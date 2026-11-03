import { useCallback, useEffect, useId, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";

import { PlatformIcon } from "../platform/PlatformIcon";
import { getLocaleTag, t } from "../../i18n/localeStore";
import { useNotifications } from "./useNotifications";
import type { NotificationRecord } from "./notificationTypes";
import "./notifications.css";

interface NotificationBellProps {
  account: string | null;
  isGuest: boolean;
  variant?: "default" | "sidebar";
}

interface PopoverPosition extends CSSProperties {
  left: number;
  top: number | "auto";
  bottom: number | "auto";
  width: number;
  maxHeight: number;
}

const POPOVER_WIDTH = 380;
const VIEWPORT_PADDING = 12;
const POPOVER_GAP = 8;
const POPOVER_MAX_HEIGHT = 520;
const POPOVER_PREFERRED_HEIGHT = 200;

export function NotificationBell({ account, isGuest, variant = "default" }: NotificationBellProps) {
  const { hasUnread, isReady, markAsRead, notifications } = useNotifications(account, isGuest);
  const [isOpen, setIsOpen] = useState(false);
  const [position, setPosition] = useState<PopoverPosition>({
    left: VIEWPORT_PADDING,
    top: VIEWPORT_PADDING,
    width: POPOVER_WIDTH,
    maxHeight: POPOVER_MAX_HEIGHT,
    bottom: "auto",
  });
  const rootRef = useRef<HTMLDivElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverId = useId();
  const titleId = `${popoverId}-title`;

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;

    const rect = trigger.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const width = Math.max(0, Math.min(POPOVER_WIDTH, viewportWidth - VIEWPORT_PADDING * 2));
    const maxLeft = Math.max(VIEWPORT_PADDING, viewportWidth - width - VIEWPORT_PADDING);
    const left = Math.max(VIEWPORT_PADDING, Math.min(rect.right - width, maxLeft));
    const availableHeight = Math.max(0, viewportHeight - VIEWPORT_PADDING * 2);
    const availableAbove = Math.max(0, rect.top - POPOVER_GAP - VIEWPORT_PADDING);
    const availableBelow = Math.max(
      0,
      viewportHeight - rect.bottom - POPOVER_GAP - VIEWPORT_PADDING,
    );

    if (availableAbove >= POPOVER_PREFERRED_HEIGHT) {
      setPosition({
        left,
        top: "auto",
        bottom: viewportHeight - rect.top + POPOVER_GAP,
        width,
        maxHeight: Math.min(POPOVER_MAX_HEIGHT, availableAbove),
      });
      return;
    }

    if (availableBelow >= POPOVER_PREFERRED_HEIGHT) {
      setPosition({
        left,
        top: rect.bottom + POPOVER_GAP,
        bottom: "auto",
        width,
        maxHeight: Math.min(POPOVER_MAX_HEIGHT, availableBelow),
      });
      return;
    }

    setPosition({
      left,
      top: VIEWPORT_PADDING,
      bottom: "auto",
      width,
      maxHeight: Math.min(POPOVER_MAX_HEIGHT, availableHeight),
    });
  }, []);

  const closePopover = useCallback((restoreFocus = false) => {
    setIsOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  function togglePopover() {
    if (isOpen) {
      closePopover();
      return;
    }

    updatePosition();
    setIsOpen(true);
  }

  useEffect(() => {
    if (!isOpen) return;

    function closeOnOutsidePointer(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (rootRef.current?.contains(target) || popoverRef.current?.contains(target)) return;
      closePopover();
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      closePopover(true);
    }

    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    document.addEventListener("pointerdown", closeOnOutsidePointer);
    document.addEventListener("keydown", closeOnEscape);
    updatePosition();

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
      document.removeEventListener("pointerdown", closeOnOutsidePointer);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [closePopover, isOpen, updatePosition]);

  return (
    <>
      <div
        className={`notification-bell${variant === "sidebar" ? " notification-bell--sidebar" : ""}`}
        data-tooltip={variant === "sidebar" ? t("通知中心") : undefined}
        ref={rootRef}
      >
        <button
          aria-controls={isOpen ? popoverId : undefined}
          aria-expanded={isOpen}
          aria-haspopup="dialog"
          aria-label={t("通知中心")}
          className={`notification-button${variant === "sidebar" ? " notification-button--sidebar" : ""}`}
          onClick={togglePopover}
          ref={triggerRef}
          type="button"
        >
          <PlatformIcon name="bell" />
          {variant === "sidebar" && (
            <span className="notification-button__label">{t("通知中心")}</span>
          )}
          {hasUnread && <span aria-hidden="true" className="notification-button__unread-dot" />}
        </button>
        <span aria-hidden="true" className="notification-bell__tooltip" role="tooltip">
          {t("通知中心")}
        </span>
      </div>

      {isOpen &&
        createPortal(
          <div
            aria-labelledby={titleId}
            className="notification-popover"
            id={popoverId}
            ref={popoverRef}
            role="dialog"
            style={position}
          >
            <div className="notification-popover__header">
              <h2 id={titleId}>{t("通知中心")}</h2>
              <button
                aria-label={t("关闭通知中心")}
                className="notification-popover__close"
                onClick={() => closePopover(true)}
                type="button"
              >
                <PlatformIcon name="close" size={18} />
              </button>
            </div>

            {!isReady ? (
              <div className="notification-popover__message" role="status">
                {t("正在加载通知…")}
              </div>
            ) : notifications.length === 0 ? (
              <div className="notification-popover__empty">
                <span aria-hidden="true" className="notification-popover__empty-icon">
                  <PlatformIcon name="bell" size={22} />
                </span>
                <strong>{t("暂无通知")}</strong>
                <p>{t("有新的系统消息时，我们会在这里通知你。")}</p>
              </div>
            ) : (
              <ul className="notification-popover__list">
                {notifications.map((notification) => (
                  <li key={notification.id}>
                    <NotificationItem notification={notification} onClick={markAsRead} />
                  </li>
                ))}
              </ul>
            )}
          </div>,
          document.body,
        )}
    </>
  );
}

function NotificationItem({
  notification,
  onClick,
}: {
  notification: NotificationRecord;
  onClick: (notificationId: string) => void;
}) {
  const translatedTitle = t(notification.title);
  const readStatus = notification.isRead ? t("已读") : t("未读");

  return (
    <button
      aria-label={`${readStatus}: ${translatedTitle}`}
      className={`notification-item${notification.isRead ? " is-read" : " is-unread"}`}
      onClick={() => onClick(notification.id)}
      type="button"
    >
      <span aria-hidden="true" className="notification-item__icon">
        <PlatformIcon name="bell" size={17} />
      </span>
      <span className="notification-item__copy">
        <span className="notification-item__meta">
          <span className="notification-item__type">{t("系统消息")}</span>
          <span className="notification-item__read-status">
            {!notification.isRead && <span aria-hidden="true" />}
            {readStatus}
          </span>
        </span>
        <strong>{translatedTitle}</strong>
        <span className="notification-item__content">{t(notification.content)}</span>
        <time className="notification-item__time" dateTime={notification.createdAt}>
          {formatNotificationTime(notification.createdAt)}
        </time>
      </span>
    </button>
  );
}

function formatNotificationTime(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return t("时间未知");

  return new Intl.DateTimeFormat(getLocaleTag(), {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
