import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setLocale } from "../../i18n/localeStore";
import { NotificationBell } from "./NotificationBell";
import {
  createNotificationUserId,
  ensureWelcomeNotification,
  loadNotifications,
  saveNotifications,
} from "./notificationStorage";

class TestTextEncoder {
  encode(value: string): Uint8Array {
    return Uint8Array.from(Array.from(value, (character) => character.charCodeAt(0)));
  }
}

beforeEach(() => {
  localStorage.clear();
  setLocale("zh-CN");
  vi.stubGlobal("TextEncoder", TestTextEncoder);
  vi.stubGlobal("crypto", {
    subtle: {
      digest: vi.fn(async (_algorithm: AlgorithmIdentifier, input: BufferSource) => {
        const bytes = new Uint8Array(input as Uint8Array);
        const account = String.fromCharCode(...bytes);
        const accountMarker = account.startsWith("alice")
          ? 0xa1
          : account.startsWith("bob")
            ? 0xb2
            : 0xc3;
        return new Uint8Array(32).fill(accountMarker).buffer;
      }),
    },
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("NotificationBell", () => {
  it("toggles the panel and closes it on outside click or Escape", async () => {
    const { container } = render(<NotificationBell account={null} isGuest />);
    const trigger = screen.getByRole("button", { name: "通知中心" });

    expect(container.querySelector('[role="tooltip"]')).toHaveTextContent("通知中心");

    fireEvent.click(trigger);
    expect(await screen.findByRole("dialog", { name: "通知中心" })).toBeInTheDocument();
    fireEvent.click(trigger);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    fireEvent.click(trigger);
    expect(await screen.findByRole("dialog", { name: "通知中心" })).toBeInTheDocument();
    fireEvent.pointerDown(document.body);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    fireEvent.click(trigger);
    expect(await screen.findByRole("dialog", { name: "通知中心" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("renders a sidebar label and opens the existing notification popover", async () => {
    render(<NotificationBell account={null} isGuest variant="sidebar" />);

    const trigger = screen.getByRole("button", { name: "通知中心" });
    expect(trigger).toHaveTextContent("通知中心");
    expect(trigger.parentElement).toHaveAttribute("data-tooltip", "通知中心");

    fireEvent.click(trigger);
    expect(await screen.findByRole("dialog", { name: "通知中心" })).toBeInTheDocument();
  });

  it("shows the empty state for a user with no notifications", async () => {
    render(<NotificationBell account={null} isGuest />);
    fireEvent.click(screen.getByRole("button", { name: "通知中心" }));

    expect(await screen.findByText("暂无通知")).toBeInTheDocument();
    expect(screen.getByText("有新的系统消息时，我们会在这里通知你。")).toBeInTheDocument();
    expect(document.querySelector(".notification-button__unread-dot")).not.toBeInTheDocument();
  });

  it("keeps the popover within a narrow mobile viewport", async () => {
    const originalWidth = window.innerWidth;
    const originalHeight = window.innerHeight;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 320 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 280 });

    try {
      render(<NotificationBell account={null} isGuest />);
      const trigger = screen.getByRole("button", { name: "通知中心" });
      vi.spyOn(trigger, "getBoundingClientRect").mockReturnValue(new DOMRect(290, 20, 24, 36));
      fireEvent.click(trigger);

      const popover = await screen.findByRole("dialog", { name: "通知中心" });
      const left = Number.parseFloat(popover.style.left);
      const top = Number.parseFloat(popover.style.top);
      const width = Number.parseFloat(popover.style.width);
      const maxHeight = Number.parseFloat(popover.style.maxHeight);

      expect(left).toBeGreaterThanOrEqual(12);
      expect(left + width).toBeLessThanOrEqual(308);
      expect(top).toBeGreaterThanOrEqual(12);
      expect(top + maxHeight).toBeLessThanOrEqual(268);
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: originalWidth });
      Object.defineProperty(window, "innerHeight", { configurable: true, value: originalHeight });
    }
  });

  it("marks a notification as read immediately and restores that state after remount", async () => {
    await ensureWelcomeNotification("member@example.com");
    const firstRender = render(<NotificationBell account="member@example.com" isGuest={false} />);
    const trigger = screen.getByRole("button", { name: "通知中心" });

    await waitFor(() =>
      expect(document.querySelector(".notification-button__unread-dot")).toBeInTheDocument(),
    );
    fireEvent.click(trigger);
    const unreadItem = await screen.findByRole("button", {
      name: "未读: 欢迎使用 OrionAI",
    });
    expect(unreadItem).toHaveClass("is-unread");
    fireEvent.click(unreadItem);

    const readItem = await screen.findByRole("button", { name: "已读: 欢迎使用 OrionAI" });
    expect(readItem).toHaveClass("is-read");
    expect(document.querySelector(".notification-button__unread-dot")).not.toBeInTheDocument();

    const userId = await createNotificationUserId("member@example.com");
    expect(loadNotifications(userId!)[0].isRead).toBe(true);

    firstRender.unmount();
    render(<NotificationBell account="member@example.com" isGuest={false} />);
    await waitFor(() =>
      expect(document.querySelector(".notification-button__unread-dot")).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "通知中心" }));
    expect(await screen.findByRole("button", { name: "已读: 欢迎使用 OrionAI" })).toHaveClass(
      "is-read",
    );
  });

  it("switches the visible unread state when the active account changes", async () => {
    const aliceId = await createNotificationUserId("alice@example.com");
    await ensureWelcomeNotification("alice@example.com");
    await ensureWelcomeNotification("bob@example.com");
    const aliceWelcome = loadNotifications(aliceId!)[0];
    saveNotifications(aliceId!, [{ ...aliceWelcome, isRead: true }]);

    const view = render(<NotificationBell account="alice@example.com" isGuest={false} />);
    const trigger = screen.getByRole("button", { name: "通知中心" });
    await waitFor(() =>
      expect(document.querySelector(".notification-button__unread-dot")).not.toBeInTheDocument(),
    );

    view.rerender(<NotificationBell account="bob@example.com" isGuest={false} />);
    await waitFor(() =>
      expect(document.querySelector(".notification-button__unread-dot")).toBeInTheDocument(),
    );
    fireEvent.click(trigger);
    expect(await screen.findByRole("button", { name: "未读: 欢迎使用 OrionAI" })).toHaveClass(
      "is-unread",
    );
  });
});
