import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ToastProvider";
import { ProfileMenu } from "./ProfileMenu";

afterEach(cleanup);

function renderSidebarMenu(overrides: Partial<ComponentProps<typeof ProfileMenu>> = {}) {
  const props: ComponentProps<typeof ProfileMenu> = {
    account: "orion@example.com",
    isLoggingOut: false,
    onLogout: vi.fn(),
    onNavigate: vi.fn(),
    triggerLabel: "侧边栏用户菜单",
    variant: "sidebar",
    ...overrides,
  };

  return { ...render(<ProfileMenu {...props} />), props };
}

describe("ProfileMenu", () => {
  it("opens and closes from the sidebar account entry", () => {
    renderSidebarMenu();

    const trigger = screen.getByRole("button", { name: "侧边栏用户菜单" });
    fireEvent.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("menu");
    expect(menu).toHaveTextContent("个人设置");
    expect(menu).toHaveTextContent("退出登录");

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveAttribute("aria-hidden", "true");
    expect(menu).toHaveAttribute("inert");

    fireEvent.animationEnd(menu);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("closes on outside pointer and Escape", () => {
    renderSidebarMenu();
    const trigger = screen.getByRole("button", { name: "侧边栏用户菜单" });

    fireEvent.click(trigger);
    fireEvent.pointerDown(document.body);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("menu", { hidden: true })).toHaveAttribute("inert");

    fireEvent.animationEnd(screen.getByRole("menu", { hidden: true }));
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: "Escape" });

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it("keeps settings navigation and logout callbacks wired", () => {
    const { props } = renderSidebarMenu();
    fireEvent.click(screen.getByRole("button", { name: "侧边栏用户菜单" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "个人设置" }));
    expect(props.onNavigate).toHaveBeenCalledWith("/settings");

    fireEvent.click(screen.getByRole("button", { name: "侧边栏用户菜单" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "安全设置" }));
    expect(props.onNavigate).toHaveBeenCalledWith("/settings/security");

    fireEvent.click(screen.getByRole("button", { name: "侧边栏用户菜单" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "退出登录" }));
    expect(props.onLogout).toHaveBeenCalledOnce();
  });

  it("opens the feedback dialog from the user menu and restores focus", async () => {
    const props: ComponentProps<typeof ProfileMenu> = {
      account: "orion@example.com",
      isLoggingOut: false,
      onLogout: vi.fn(),
      onNavigate: vi.fn(),
      triggerLabel: "侧边栏用户菜单",
      variant: "sidebar",
    };
    render(
      <ToastProvider>
        <ProfileMenu {...props} />
      </ToastProvider>,
    );
    const trigger = screen.getByRole("button", { name: "侧边栏用户菜单" });
    fireEvent.click(trigger);
    expect(screen.getByRole("menu")).toHaveTextContent("问题反馈");

    fireEvent.click(screen.getByRole("menuitem", { name: "问题反馈" }));

    expect(screen.getByRole("dialog", { name: "问题反馈" })).toBeInTheDocument();
    expect(screen.getByLabelText("标题")).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "关闭问题反馈" }));
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("shows the latest nickname and avatar supplied by the profile", () => {
    const { container } = renderSidebarMenu({
      nickname: "更新后的昵称",
      avatarUrl: "https://oss.example/avatar.png",
    });
    fireEvent.click(screen.getByRole("button", { name: "侧边栏用户菜单" }));

    expect(screen.getAllByText("更新后的昵称")).toHaveLength(2);
    expect(container.querySelector("img")).toHaveAttribute("src", "https://oss.example/avatar.png");
  });
});
