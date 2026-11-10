import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HomeCapabilitiesSection } from "./HomeCapabilitiesSection";

describe("HomeCapabilitiesSection", () => {
  it("renders the six requested capabilities and invokes the existing auth flow", () => {
    const onRequireAuth = vi.fn();
    render(<HomeCapabilitiesSection onRequireAuth={onRequireAuth} />);

    expect(
      screen.getByRole("heading", { name: "不止于对话，让 AI 真正完成任务" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(6);
    expect(screen.getAllByRole("article")[3]).toHaveTextContent(
      /记住你的偏好与上下文\s+提供更个性化的服务/,
    );

    fireEvent.click(screen.getByRole("button", { name: "开启你的 AI 探索之旅" }));
    expect(onRequireAuth).toHaveBeenCalledOnce();
  });
});
