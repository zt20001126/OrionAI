import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DigitalHumanLoadingOverlay } from "./DigitalHumanLoadingOverlay";

afterEach(cleanup);
describe("DigitalHumanLoadingOverlay", () => {
  it("只在下载长度已知时展示真实百分比，初始化时使用不确定进度", () => {
    const view = render(
      <DigitalHumanLoadingOverlay phase="loading" progress={42} onRetry={vi.fn()} />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByText("42%")).toBeInTheDocument();
    view.rerender(
      <DigitalHumanLoadingOverlay phase="initializing" progress={100} onRetry={vi.fn()} />,
    );
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText("100%")).not.toBeInTheDocument();
  });
  it("失败时提供局部重试", () => {
    const retry = vi.fn();
    render(<DigitalHumanLoadingOverlay phase="error" progress={null} onRetry={retry} />);
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});
