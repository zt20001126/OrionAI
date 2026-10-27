import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileSettingsPage } from "./ProfileSettingsPage";
import { getUserProfile, updateUserProfile, type UserProfile } from "./profileApi";

vi.mock("./profileApi", () => ({
  getUserProfile: vi.fn(),
  updateUserProfile: vi.fn(),
}));

const defaultProfile: UserProfile = {
  nickname: "示例用户",
  account: "user@example.com",
  avatar_url: "/avatar/default_avatar.png",
  created_at: "2025-03-10T14:26:08+08:00",
  last_login_at: "2026-01-26T09:17:34+08:00",
};

afterEach(cleanup);

beforeEach(() => {
  vi.mocked(getUserProfile).mockResolvedValue(defaultProfile);
  vi.mocked(updateUserProfile).mockResolvedValue(defaultProfile);
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:avatar-preview"),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    value: vi.fn(),
  });
});

describe("ProfileSettingsPage", () => {
  it("shows the default avatar and keeps account and timestamps read-only", async () => {
    render(<ProfileSettingsPage />);

    expect(await screen.findByRole("heading", { name: "个人设置" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "示例用户 的头像" })).toHaveAttribute(
      "src",
      "/avatar/default_avatar.png",
    );
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
    expect(screen.getByText("2025-03-10 14:26:08")).toBeInTheDocument();
    expect(screen.getByText("2026-01-26 09:17:34")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "用户昵称" })).toHaveValue("示例用户");
  });

  it("previews an avatar locally and discards it when cancelled", async () => {
    render(<ProfileSettingsPage />);
    await screen.findByRole("heading", { name: "个人设置" });
    const file = new File(["image-bytes"], "avatar.png", { type: "image/png" });

    fireEvent.change(screen.getByLabelText("选择头像文件"), { target: { files: [file] } });

    expect(screen.getByRole("button", { name: "更换头像" })).toHaveFocus();
    expect(screen.getByRole("img", { name: "示例用户 的头像" })).toHaveAttribute(
      "src",
      "blob:avatar-preview",
    );
    expect(updateUserProfile).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    expect(screen.getByRole("img", { name: "示例用户 的头像" })).toHaveAttribute(
      "src",
      "/avatar/default_avatar.png",
    );
  });

  it("saves the nickname and selected avatar together", async () => {
    const updatedProfile = { ...defaultProfile, nickname: "新昵称", avatar_url: "https://oss.example/avatar.png" };
    vi.mocked(updateUserProfile).mockResolvedValue(updatedProfile);
    render(<ProfileSettingsPage />);
    await screen.findByRole("heading", { name: "个人设置" });
    const avatar = new File(["image-bytes"], "avatar.png", { type: "image/png" });

    fireEvent.change(screen.getByRole("textbox", { name: "用户昵称" }), {
      target: { value: "新昵称" },
    });
    fireEvent.change(screen.getByLabelText("选择头像文件"), { target: { files: [avatar] } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(updateUserProfile).toHaveBeenCalledWith("新昵称", avatar));
    expect(await screen.findByText("个人资料已保存。")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "新昵称 的头像" })).toHaveAttribute(
      "src",
      "https://oss.example/avatar.png",
    );
  });

  it("limits the nickname to 20 characters", async () => {
    render(<ProfileSettingsPage />);
    await screen.findByRole("heading", { name: "个人设置" });

    const nicknameInput = screen.getByRole("textbox", { name: "用户昵称" });
    expect(nicknameInput).toHaveAttribute("maxLength", "20");
    fireEvent.change(nicknameInput, { target: { value: "a".repeat(20) } });
    expect(nicknameInput).toHaveValue("a".repeat(20));
    expect(screen.getByText("20/20")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存" })).toBeEnabled();
  });

  it("keeps edits available and shows an error if saving fails", async () => {
    vi.mocked(updateUserProfile).mockRejectedValue(new Error("OSS 暂时不可用。"));
    render(<ProfileSettingsPage />);
    await screen.findByRole("heading", { name: "个人设置" });
    const nicknameInput = screen.getByRole("textbox", { name: "用户昵称" });
    fireEvent.change(nicknameInput, { target: { value: "待保存昵称" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("OSS 暂时不可用。");
    expect(nicknameInput).toHaveValue("待保存昵称");
  });
});
