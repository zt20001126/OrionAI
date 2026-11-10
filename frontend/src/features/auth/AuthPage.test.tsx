import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ToastProvider";
import { setLocale } from "../../i18n/localeStore";
import { login, register } from "./authApi";
import { AuthPage } from "./AuthPage";

vi.mock("./authApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./authApi")>();
  return {
    ...actual,
    login: vi.fn(),
    register: vi.fn(),
  };
});
vi.mock("../digital-human/components/DigitalHumanAvatar3D", () => ({
  DigitalHumanAvatar3D: () => <div data-testid="auth-avatar" />,
}));

afterEach(() => {
  cleanup();
  setLocale("zh-CN");
});

describe("AuthPage", () => {
  it("shows only the centered brand lockup and title in the left product area", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    const productPanel = screen.getByRole("complementary", { name: "探索 AI 的更多可能" });
    expect(productPanel).toHaveTextContent("OrionAI");
    expect(
      within(productPanel).getByRole("heading", { name: "探索 AI 的更多可能" }),
    ).toBeInTheDocument();
    expect(within(productPanel).getByRole("button", { name: "显示测试账号" })).toBeInTheDocument();
    expect(productPanel).not.toHaveTextContent("一站式 AI 智能体与工具平台");
    expect(productPanel).not.toHaveTextContent("丰富的智能体");
    expect(productPanel).not.toHaveTextContent("探索技能市场");
  });

  it("keeps the demo account hidden until the product logo is clicked", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    expect(screen.queryByRole("dialog", { name: "测试账号" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "显示测试账号" }));
    expect(screen.getByRole("dialog", { name: "测试账号" })).toBeInTheDocument();
  });

  it("offers Gitee sign in from the login view", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    expect(screen.getByRole("link", { name: "使用 Gitee 登录" })).toHaveAttribute(
      "href",
      "/api/v1/auth/gitee/login",
    );
  });

  it("returns protected showcase actions to the existing login card without clearing input", () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.change(screen.getByLabelText("邮箱"), { target: { value: "orion@example.com" } });
    fireEvent.click(screen.getByRole("textbox", { name: "请先登录后开始对话" }));

    expect(scrollIntoView).toHaveBeenCalledOnce();
    expect(document.querySelector(".auth-card")).toHaveClass("is-auth-highlighted");
    expect(screen.getByLabelText("邮箱")).toHaveValue("orion@example.com");
    expect(screen.getByRole("tab", { name: "登录" })).toHaveAttribute("aria-selected", "true");
    Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
  });

  it("shows the demo account dialog on demand without an inline notice", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "显示测试账号" }));
    expect(screen.getByRole("dialog", { name: "测试账号" })).toBeInTheDocument();
    expect(screen.getByText("admin@admin.com")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制账号" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复制密码" })).toBeInTheDocument();
    expect(screen.queryByText("账号")).not.toBeInTheDocument();
    expect(
      screen.queryByText("可体验会员功能。此账号为共享演示数据，请勿保存个人信息。"),
    ).not.toBeInTheDocument();
    expect(document.querySelector(".auth-demo-notice")).not.toBeInTheDocument();
    expect(screen.getByLabelText("邮箱")).toHaveAttribute("type", "email");
  });

  it("closes with Escape and does not reopen after changing auth views", async () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "显示测试账号" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "测试账号" })).not.toBeInTheDocument();
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

    fireEvent.click(screen.getByRole("button", { name: "显示测试账号" }));
    fireEvent.click(screen.getByRole("button", { name: "我知道了" }));

    expect(screen.queryByRole("dialog", { name: "测试账号" })).not.toBeInTheDocument();
  });

  it("starts keyboard focus in the dialog and keeps focus inside it", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "显示测试账号" }));
    const closeButton = screen.getByRole("button", { name: "关闭测试账号弹窗" });
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

    fireEvent.click(screen.getByRole("button", { name: "显示测试账号" }));
    fireEvent.click(screen.getByRole("button", { name: "关闭测试账号弹窗" }));

    expect(screen.queryByRole("dialog", { name: "测试账号" })).not.toBeInTheDocument();
  });

  it("copies the account and password and reports success or failure", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: "显示测试账号" }));
    fireEvent.click(screen.getByRole("button", { name: "复制账号" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("admin@admin.com"));
    expect(await screen.findByText("复制成功。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "复制密码" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("admin"));
    expect(await screen.findByText("复制成功。")).toBeInTheDocument();

    writeText.mockRejectedValueOnce(new Error("clipboard unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "复制密码" }));
    expect(await screen.findByText("复制失败，请重试。")).toBeInTheDocument();
  });

  it("updates the test account dialog text when the language changes", () => {
    setLocale("zh-CN");

    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "显示测试账号" }));
    expect(screen.getByRole("dialog", { name: "测试账号" })).toBeInTheDocument();
    act(() => setLocale("en"));

    expect(screen.getByRole("dialog", { name: "Test Account" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Got it" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy password" })).toBeInTheDocument();

    setLocale("zh-CN");
  });

  it("keeps email-only validation on registration", () => {
    render(
      <ToastProvider>
        <AuthPage onAuthenticated={vi.fn()} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("tab", { name: "注册" }));

    expect(screen.getByLabelText("邮箱")).toHaveAttribute("type", "email");
  });

  it("identifies an interactive login separately from restored sessions", async () => {
    vi.mocked(login).mockResolvedValue({ account: "member@example.com" });
    const onAuthenticated = vi.fn();

    render(
      <ToastProvider>
        <AuthPage onAuthenticated={onAuthenticated} />
      </ToastProvider>,
    );

    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "member@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "password" } });
    fireEvent.submit(screen.getByRole("tabpanel").closest("form")!);

    await waitFor(() =>
      expect(onAuthenticated).toHaveBeenCalledWith(
        { account: "member@example.com", is_guest: false },
        "login",
      ),
    );
  });

  it("identifies a successful registration so only that flow creates the welcome notice", async () => {
    vi.mocked(register).mockResolvedValue({ account: "new-member@example.com" });
    const onAuthenticated = vi.fn();

    render(
      <ToastProvider>
        <AuthPage onAuthenticated={onAuthenticated} />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("tab", { name: "注册" }));
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "new-member@example.com" },
    });
    fireEvent.change(screen.getByLabelText("邮箱验证码"), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "password123" } });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "password123" },
    });
    fireEvent.submit(screen.getByRole("tabpanel").closest("form")!);

    await waitFor(() =>
      expect(onAuthenticated).toHaveBeenCalledWith(
        { account: "new-member@example.com", is_guest: false },
        "register",
      ),
    );
  });
});
