import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { changePassword, sendPasswordChangeCode } from "./profileApi";
import { SecuritySettingsPage } from "./SecuritySettingsPage";
import { ToastProvider } from "../../components/ToastProvider";

vi.mock("./profileApi", () => ({
  changePassword: vi.fn(),
  sendPasswordChangeCode: vi.fn(),
}));

afterEach(cleanup);

function renderWithToast(ui: ReactNode) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

beforeEach(() => {
  vi.mocked(sendPasswordChangeCode).mockResolvedValue({ message: "验证码已发送。" });
  vi.mocked(changePassword).mockResolvedValue({ message: "密码已修改，请使用新密码重新登录。" });
});

describe("SecuritySettingsPage", () => {
  it("shows the bound account and sends a code without accepting an email input", async () => {
    renderWithToast(
      <SecuritySettingsPage account="person@example.com" onPasswordChanged={vi.fn()} />,
    );

    expect(screen.getByLabelText("绑定邮箱")).toHaveAttribute("readonly");
    fireEvent.click(screen.getByRole("button", { name: "发送验证码" }));

    await waitFor(() => expect(sendPasswordChangeCode).toHaveBeenCalledOnce());
    expect(await screen.findByText("验证码已发送。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /秒后重发/ })).toBeDisabled();
  });

  it("submits matching password fields and clears them before requiring sign in again", async () => {
    const onPasswordChanged = vi.fn();
    renderWithToast(
      <SecuritySettingsPage account="person@example.com" onPasswordChanged={onPasswordChanged} />,
    );
    fireEvent.change(screen.getByLabelText("新密码"), {
      target: { value: "new secure password" },
    });
    fireEvent.change(screen.getByLabelText("确认新密码"), {
      target: { value: "new secure password" },
    });
    fireEvent.change(screen.getByLabelText("邮箱验证码"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认修改" }));

    await waitFor(() =>
      expect(changePassword).toHaveBeenCalledWith({
        code: "123456",
        new_password: "new secure password",
        password_confirmation: "new secure password",
      }),
    );
    expect(onPasswordChanged).toHaveBeenCalledWith("密码已修改，请使用新密码重新登录。");
    expect(screen.getByLabelText("新密码")).toHaveValue("");
    expect(screen.getByLabelText("确认新密码")).toHaveValue("");
    expect(screen.getByLabelText("邮箱验证码")).toHaveValue("");
  });

  it("keeps passwords with surrounding spaces unchanged and rejects a mismatch", async () => {
    renderWithToast(
      <SecuritySettingsPage account="person@example.com" onPasswordChanged={vi.fn()} />,
    );
    fireEvent.change(screen.getByLabelText("新密码"), {
      target: { value: " 1234567 " },
    });
    fireEvent.change(screen.getByLabelText("确认新密码"), {
      target: { value: "1234567 " },
    });
    fireEvent.change(screen.getByLabelText("邮箱验证码"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认修改" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("两次输入的密码不一致");
    expect(changePassword).not.toHaveBeenCalled();
  });
});
