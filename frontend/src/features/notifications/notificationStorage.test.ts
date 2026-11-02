import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createNotificationUserId,
  ensureWelcomeNotification,
  loadNotifications,
  saveNotifications,
} from "./notificationStorage";
import type { NotificationRecord } from "./notificationTypes";

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("crypto", {
    subtle: {
      digest: vi.fn().mockResolvedValue(new Uint8Array([0x12, 0xab]).buffer),
    },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("notificationStorage", () => {
  it("creates one persistent welcome notification without storing the account", async () => {
    const account = "Member@Example.com";
    const userId = await createNotificationUserId(account);

    expect(userId).toBe("account-sha256-12ab");

    await ensureWelcomeNotification(account);
    const [welcomeNotification] = loadNotifications(userId!);

    expect(welcomeNotification).toMatchObject({
      id: "system-welcome-v1",
      userId,
      type: "system",
      title: "欢迎使用 OrionAI",
      content: "欢迎来到 OrionAI！探索技能市场，添加你感兴趣的 AI 智能体和工具，开启智能体验。",
      isRead: false,
    });
    expect(Number.isNaN(Date.parse(welcomeNotification.createdAt))).toBe(false);
    expect(localStorage.key(0)).not.toContain(account);

    saveNotifications(userId!, [{ ...welcomeNotification, isRead: true }]);
    await ensureWelcomeNotification(account);

    expect(loadNotifications(userId!)).toHaveLength(1);
    expect(loadNotifications(userId!)[0].isRead).toBe(true);
  });

  it("keeps notification lists isolated by user ID and sorts newest first", () => {
    const notification = (id: string, userId: string, createdAt: string): NotificationRecord => ({
      id,
      userId,
      type: "system",
      title: id,
      content: "content",
      createdAt,
      isRead: false,
    });

    saveNotifications("user-a", [
      notification("older", "user-a", "2026-01-01T00:00:00.000Z"),
      notification("newer", "user-a", "2026-02-01T00:00:00.000Z"),
      notification("other-user", "user-b", "2026-03-01T00:00:00.000Z"),
    ]);
    saveNotifications("user-b", [notification("other-user", "user-b", "2026-03-01T00:00:00.000Z")]);

    expect(loadNotifications("user-a").map(({ id }) => id)).toEqual(["newer", "older"]);
    expect(loadNotifications("user-b").map(({ id }) => id)).toEqual(["other-user"]);
  });

  it("handles malformed JSON and unavailable local storage safely", async () => {
    localStorage.setItem("orionai:notifications:v1:user-a", "{");
    expect(loadNotifications("user-a")).toEqual([]);

    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage blocked");
    });

    expect(loadNotifications("user-a")).toEqual([]);
    expect(() => saveNotifications("user-a", [])).not.toThrow();
    await expect(ensureWelcomeNotification("member@example.com")).resolves.toBeUndefined();
  });
});
