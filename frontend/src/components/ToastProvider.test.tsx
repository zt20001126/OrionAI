import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./ToastProvider";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function ToastTrigger() {
  const { showToast } = useToast();

  return (
    <>
      <button onClick={() => showToast("error", "第一条错误")} type="button">
        显示第一条
      </button>
      <button onClick={() => showToast("error", "第二条错误")} type="button">
        显示第二条
      </button>
    </>
  );
}

describe("ToastProvider", () => {
  it("replaces an active toast and restarts the display and exit timers", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "显示第一条" }));
    expect(screen.getByRole("alert")).toHaveTextContent("第一条错误");

    act(() => vi.advanceTimersByTime(1900));
    fireEvent.click(screen.getByRole("button", { name: "显示第二条" }));
    expect(screen.getByRole("alert")).toHaveTextContent("第二条错误");
    expect(screen.queryByText("第一条错误")).not.toBeInTheDocument();

    act(() => vi.advanceTimersByTime(2199));
    expect(screen.getByRole("alert")).not.toHaveClass("is-exiting");

    act(() => vi.advanceTimersByTime(1));
    expect(screen.getByRole("alert")).toHaveClass("is-exiting");

    act(() => vi.advanceTimersByTime(299));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears timers when the provider unmounts", () => {
    vi.useFakeTimers();
    const { unmount } = render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "显示第一条" }));
    unmount();

    expect(() => act(() => vi.runOnlyPendingTimers())).not.toThrow();
  });
});
