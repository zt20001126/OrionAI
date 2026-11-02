import type { NotificationRecord } from "./notificationTypes";

const STORAGE_KEY_PREFIX = "orionai:notifications:v1:";
const WELCOME_NOTIFICATION_ID = "system-welcome-v1";
const WELCOME_NOTIFICATION_TITLE = "欢迎使用 OrionAI";
const WELCOME_NOTIFICATION_CONTENT =
  "欢迎来到 OrionAI！探索技能市场，添加你感兴趣的 AI 智能体和工具，开启智能体验。";

export async function createNotificationUserId(account: string): Promise<string | null> {
  const normalizedAccount = account.trim().toLowerCase();
  const subtleCrypto = globalThis.crypto?.subtle;
  if (!normalizedAccount || !subtleCrypto || typeof TextEncoder === "undefined") return null;

  try {
    const digest = await subtleCrypto.digest(
      "SHA-256",
      new TextEncoder().encode(normalizedAccount),
    );
    const digestHex = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
    return `account-sha256-${digestHex}`;
  } catch {
    return null;
  }
}

export function loadNotifications(userId: string): NotificationRecord[] {
  const storage = getLocalStorage();
  if (!storage) return [];

  try {
    const rawValue = storage.getItem(getStorageKey(userId));
    if (!rawValue) return [];

    const parsedValue: unknown = JSON.parse(rawValue);
    if (!Array.isArray(parsedValue)) return [];

    return sortNotifications(
      parsedValue.filter((value): value is NotificationRecord => isNotification(value, userId)),
    );
  } catch {
    return [];
  }
}

export function saveNotifications(userId: string, notifications: NotificationRecord[]): void {
  const storage = getLocalStorage();
  if (!storage) return;

  try {
    const safeNotifications = sortNotifications(
      notifications.filter((notification) => isNotification(notification, userId)),
    );
    storage.setItem(getStorageKey(userId), JSON.stringify(safeNotifications));
  } catch {
    // 通知仅保存在本地；存储不可用时仍允许当前页面正常使用。
  }
}

export async function ensureWelcomeNotification(account: string): Promise<void> {
  try {
    const userId = await createNotificationUserId(account);
    if (!userId) return;

    const notifications = loadNotifications(userId);
    if (notifications.some((notification) => notification.id === WELCOME_NOTIFICATION_ID)) return;

    const welcomeNotification: NotificationRecord = {
      id: WELCOME_NOTIFICATION_ID,
      userId,
      type: "system",
      title: WELCOME_NOTIFICATION_TITLE,
      content: WELCOME_NOTIFICATION_CONTENT,
      createdAt: new Date().toISOString(),
      isRead: false,
    };
    saveNotifications(userId, [...notifications, welcomeNotification]);
  } catch {
    // 注册不应因通知初始化或本地存储失败而中断。
  }
}

export function sortNotifications(notifications: NotificationRecord[]): NotificationRecord[] {
  return [...notifications].sort((left, right) => {
    const leftTime = Date.parse(left.createdAt);
    const rightTime = Date.parse(right.createdAt);
    const safeLeftTime = Number.isFinite(leftTime) ? leftTime : 0;
    const safeRightTime = Number.isFinite(rightTime) ? rightTime : 0;
    return safeRightTime - safeLeftTime;
  });
}

function isNotification(value: unknown, userId: string): value is NotificationRecord {
  if (!value || typeof value !== "object") return false;
  const notification = value as Partial<NotificationRecord>;
  return (
    notification.userId === userId &&
    typeof notification.id === "string" &&
    notification.type === "system" &&
    typeof notification.title === "string" &&
    typeof notification.content === "string" &&
    typeof notification.createdAt === "string" &&
    typeof notification.isRead === "boolean"
  );
}

function getStorageKey(userId: string): string {
  return `${STORAGE_KEY_PREFIX}${userId}`;
}

function getLocalStorage(): Storage | null {
  if (typeof window === "undefined") return null;

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}
