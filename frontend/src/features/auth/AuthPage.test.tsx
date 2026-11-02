import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ToastProvider";
import { AuthPage } from "./AuthPage";

afterEach(cleanup);

describe("AuthPage", () => {
  it("shows the demo account dialog on login without an inline notice", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    expect(screen.getByRole("dialog", { name: "体验账号" })).toBeInTheDocument();
    expect(screen.getByText("admin@admin.com")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(
      screen.getByText("可体验会员功能。此账号为共享演示数据，请勿保存个人信息。"),
    ).toBeInTheDocument();
    expect(document.querySelector(".auth-demo-notice")).not.toBeInTheDocument();
    expect(screen.getByLabelText("邮箱")).toHaveAttribute("type", "email");
  });

  it("closes with Escape and does not reopen after changing auth views", async () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "体验账号" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("邮箱")).toHaveFocus());

    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.querySelector(".auth-demo-notice")).not.toBeInTheDocument();
    expect(screen.getByLabelText("邮箱")).toHaveAttribute("type", "email");

    fireEvent.click(screen.getByRole("tab", { name: "登录" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes with the acknowledgement button", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "我知道了" }));

    expect(screen.queryByRole("dialog", { name: "体验账号" })).not.toBeInTheDocument();
  });

  it("starts keyboard focus in the dialog and keeps focus inside it", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    const closeButton = screen.getByRole("button", { name: "关闭体验账号提示" });
    const acknowledgeButton = screen.getByRole("button", { name: "我知道了" });
    expect(closeButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });

    expect(acknowledgeButton).toHaveFocus();
  });

  it("closes with the dialog close button", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "关闭体验账号提示" }));

    expect(screen.queryByRole("dialog", { name: "体验账号" })).not.toBeInTheDocument();
  });

  it("copies the demo account and reports success or failure", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "复制账号" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("admin@admin.com"));
    expect(await screen.findByText("体验账号已复制。")).toBeInTheDocument();

    writeText.mockRejectedValueOnce(new Error("clipboard unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "复制账号" }));
    expect(await screen.findByText("复制失败，请手动复制账号。")).toBeInTheDocument();
  });

  it("keeps email-only validation on registration", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "我知道了" }));
    fireEvent.click(screen.getByRole("tab", { name: "注册" }));

    expect(screen.getByLabelText("邮箱")).toHaveAttribute("type", "email");
  });
});
