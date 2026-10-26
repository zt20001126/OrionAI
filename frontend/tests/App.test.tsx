import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

    expect(await screen.findByRole("heading", { name: "欢迎回来" })).toBeInTheDocument();
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
});
