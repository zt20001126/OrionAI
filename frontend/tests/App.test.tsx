import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/app/App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("OrionAI authentication page", () => {
  it("restores an anonymous session and logs in with a cookie-backed request", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith("/api/v1/skills")) {
        return {
          ok: true,
          json: async () => ({ items: [], total: 0, page: 1, page_size: 100 }),
        } as Response;
      }
      if (path.endsWith("/session")) {
        return {
          ok: true,
          json: async () => ({ authenticated: false, account: null }),
        } as Response;
      }
      return { ok: true, json: async () => ({ account: "person@example.com" }) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "登录 OrionAI" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "person@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "correct horse battery" } });
    fireEvent.click(screen.getByRole("button", { name: "显示密码" }));
    expect(screen.getByLabelText("密码")).toHaveAttribute("type", "text");
    fireEvent.click(screen.getByRole("button", { name: "隐藏密码" }));
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(
      await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/market");
    const loginCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/login"));
    expect(loginCall?.[1]).toMatchObject({ credentials: "include" });
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({
      email: "person@example.com",
      password: "correct horse battery",
    });
  });

  it("requests a registration code and shows the resend cooldown", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/session")) {
        return {
          ok: true,
          json: async () => ({ authenticated: false, account: null }),
        } as Response;
      }
      return { ok: true, json: async () => ({ message: "验证码已发送。" }) } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "注册" }));
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "person@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));

    expect(await screen.findByRole("status")).toHaveTextContent("验证码已发送");
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /秒后重发/ })).toBeDisabled();
    });
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/email-codes"))).toBe(
      true,
    );
  });

  it("shows login errors in a toast outside the authentication card", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/session")) {
        return {
          ok: true,
          json: async () => ({ authenticated: false, account: null }),
        } as Response;
      }
      return {
        ok: false,
        status: 401,
        json: async () => ({ detail: "邮箱或密码错误。" }),
      } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    const card = await screen.findByRole("region", { name: "登录 OrionAI" });
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "person@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "incorrect password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("邮箱或密码错误。");
    expect(within(card).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("hides technical server details behind a safe authentication message", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/session")) {
        return {
          ok: true,
          json: async () => ({ authenticated: false, account: null }),
        } as Response;
      }
      return {
        ok: false,
        status: 500,
        json: async () => ({ detail: "Traceback: SQL connection secret details" }),
      } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByRole("heading", { name: "登录 OrionAI" });
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "person@example.com" },
    });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "incorrect password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("认证服务暂不可用");
    expect(screen.queryByText(/SQL connection secret details/)).not.toBeInTheDocument();
  });

  it("routes registration and password reset failures through the same toast", async () => {
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith("/session")) {
        return {
          ok: true,
          json: async () => ({ authenticated: false, account: null }),
        } as Response;
      }
      if (path.endsWith("/email-codes")) {
        return {
          ok: false,
          status: 429,
          json: async () => ({ detail: "请求过于频繁，请稍后重试。" }),
        } as Response;
      }
      if (path.endsWith("/register")) {
        return {
          ok: false,
          status: 400,
          json: async () => ({ detail: "验证码无效或已过期。" }),
        } as Response;
      }
      return {
        ok: false,
        status: 400,
        json: async () => ({ detail: "密码重置验证码无效或已过期。" }),
      } as Response;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "注册" }));
    fireEvent.change(screen.getByLabelText("邮箱"), {
      target: { value: "person@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "获取验证码" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请求过于频繁");

    fireEvent.change(screen.getByLabelText("邮箱验证码"), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "new-password-123" } });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "new-password-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建账号" }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("验证码无效或已过期");
    });

    fireEvent.click(screen.getByRole("tab", { name: "登录" }));
    fireEvent.click(screen.getByRole("button", { name: "忘记密码？" }));
    fireEvent.change(screen.getByLabelText("邮箱验证码"), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "new-password-456" } });
    fireEvent.change(screen.getByLabelText("确认密码"), {
      target: { value: "new-password-456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "更新密码" }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("密码重置验证码无效或已过期");
    });

    const card = screen.getByRole("region", { name: "重置密码" });
    expect(within(card).queryByRole("alert")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/password-reset"))).toBe(
      true,
    );
  });
});
