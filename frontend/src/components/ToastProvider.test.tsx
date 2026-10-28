import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider, useToast } from "./ToastProvider";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function ToastTrigger() {
  const { confirm, showToast } = useToast();

  return (
    <>
      <button onClick={() => showToast("error", "第一条错误")} type="button">
        显示第一条
      </button>
      <button onClick={() => showToast("error", "第二条错误")} type="button">
        显示第二条
      </button>
      <button
        onClick={() => void confirm({ title: "确认操作？", description: "请确认是否继续。" })}
        type="button"
      >
        打开确认框
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

  it("allows a toast to be dismissed manually", () => {
    vi.useFakeTimers();
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "显示第一条" }));
    fireEvent.click(screen.getByRole("button", { name: "关闭提示" }));

    expect(screen.getByRole("alert")).toHaveClass("is-exiting");
    act(() => vi.advanceTimersByTime(300));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a confirmation dialog and closes it with Escape", async () => {
    render(
      <ToastProvider>
        <ToastTrigger />
      </ToastProvider>,
    );
    const trigger = screen.getByRole("button", { name: "打开确认框" });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog", { name: "确认操作？" });
    expect(dialog).toHaveTextContent("请确认是否继续。");
    expect(screen.getByRole("button", { name: "取消" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("waits for an asynchronous confirmation action and prevents duplicate submits", async () => {
    let finishConfirmation: ((confirmed: boolean) => void) | undefined;
    const onConfirm = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          finishConfirmation = resolve;
        }),
    );
    function AsyncConfirmTrigger() {
      const { confirm } = useToast();
      return (
        <button
          onClick={() =>
            void confirm({
              title: "保存并继续？",
              description: "保存后继续执行。",
              confirmLabel: "保存并继续",
              onConfirm,
            })
          }
          type="button"
        >
          执行异步确认
        </button>
      );
    }

    render(
      <ToastProvider>
        <AsyncConfirmTrigger />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "执行异步确认" }));
    fireEvent.click(screen.getByRole("button", { name: "保存并继续" }));

    expect(await screen.findByRole("button", { name: "处理中…" })).toBeDisabled();
    expect(onConfirm).toHaveBeenCalledOnce();
    finishConfirmation?.(true);

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
