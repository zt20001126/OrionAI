import { useCallback, useEffect, useRef, useState } from "react";

import {
  createNotificationUserId,
  loadNotifications,
  saveNotifications,
} from "./notificationStorage";
import type { NotificationRecord } from "./notificationTypes";

interface NotificationSnapshot {
  accountKey: string | null;
  userId: string | null;
  notifications: NotificationRecord[];
}

interface UseNotificationsResult {
  hasUnread: boolean;
  isReady: boolean;
  markAsRead: (notificationId: string) => void;
  notifications: NotificationRecord[];
}

export function useNotifications(account: string | null, isGuest: boolean): UseNotificationsResult {
  const accountKey = !isGuest ? normalizeAccount(account) : null;
  const [snapshot, setSnapshot] = useState<NotificationSnapshot>({
    accountKey: null,
    userId: null,
    notifications: [],
  });
  const snapshotRef = useRef(snapshot);

  useEffect(() => {
    let isActive = true;

    if (!accountKey) {
      return () => {
        isActive = false;
      };
    }

    void createNotificationUserId(accountKey)
      .then((userId) => {
        if (!isActive) return;
        const nextSnapshot: NotificationSnapshot = {
          accountKey,
          userId,
          notifications: userId ? loadNotifications(userId) : [],
        };
        snapshotRef.current = nextSnapshot;
        setSnapshot(nextSnapshot);
      })
      .catch(() => {
        if (!isActive) return;
        const nextSnapshot: NotificationSnapshot = { accountKey, userId: null, notifications: [] };
        snapshotRef.current = nextSnapshot;
        setSnapshot(nextSnapshot);
      });

    return () => {
      isActive = false;
    };
  }, [accountKey]);

  const markAsRead = useCallback(
    (notificationId: string) => {
      const current = snapshotRef.current;
      if (!accountKey || current.accountKey !== accountKey || !current.userId) return;

      const selectedNotification = current.notifications.find(
        (notification) => notification.id === notificationId,
      );
      if (!selectedNotification || selectedNotification.isRead) return;

      const nextSnapshot: NotificationSnapshot = {
        ...current,
        notifications: current.notifications.map((notification) =>
          notification.id === notificationId ? { ...notification, isRead: true } : notification,
        ),
      };
      saveNotifications(current.userId, nextSnapshot.notifications);
      snapshotRef.current = nextSnapshot;
      setSnapshot(nextSnapshot);
    },
    [accountKey],
  );

  const isReady = !accountKey || snapshot.accountKey === accountKey;
  const notifications =
    accountKey && snapshot.accountKey === accountKey ? snapshot.notifications : [];

  return {
    hasUnread: notifications.some((notification) => !notification.isRead),
    isReady,
    markAsRead,
    notifications,
  };
}

function normalizeAccount(account: string | null): string | null {
  const normalizedAccount = account?.trim().toLowerCase();
  return normalizedAccount || null;
}
