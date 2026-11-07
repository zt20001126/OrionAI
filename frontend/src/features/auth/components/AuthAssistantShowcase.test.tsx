import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthAssistantShowcase } from "./AuthAssistantShowcase";

vi.mock("../../digital-human/hooks/useVrmPointerLookTarget", () => ({
  useVrmPointerLookTarget: () => ({ current: null }),
}));
vi.mock("../../digital-human/components/DigitalHumanAvatar3D", () => ({
  DigitalHumanAvatar3D: () => <div data-testid="showcase-avatar" />,
}));

afterEach(cleanup);

describe("AuthAssistantShowcase", () => {
  it("allows feature details to expand and gates execution behind sign-in", async () => {
    const onRequireAuth = vi.fn();
    render(<AuthAssistantShowcase onRequireAuth={onRequireAuth} />);

    fireEvent.click(screen.getByRole("button", { name: /生成图片/ }));
    expect(screen.getByText(/帮我生成一张晴天海边的插画/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "登录后体验" }));
    expect(onRequireAuth).toHaveBeenCalledOnce();
  });

  it("returns to sign-in from the composer without activating voice capture", () => {
    const onRequireAuth = vi.fn();
    render(<AuthAssistantShowcase onRequireAuth={onRequireAuth} />);

    fireEvent.click(screen.getByRole("textbox", { name: "请先登录后开始对话" }));
    fireEvent.click(screen.getByRole("button", { name: "登录后使用语音" }));
    fireEvent.click(screen.getByRole("button", { name: "登录后发送消息" }));

    expect(onRequireAuth).toHaveBeenCalledTimes(3);
  });

  it("can collapse and restore the feature cards", () => {
    render(<AuthAssistantShowcase onRequireAuth={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "跳过引导" }));
    expect(screen.queryByRole("button", { name: /生成图片/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重新显示能力" }));
    expect(screen.getByRole("button", { name: /生成图片/ })).toBeInTheDocument();
  });
});
