import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ToastProvider";
import { FeedbackDialog } from "./FeedbackDialog";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderDialog() {
  const onClose = vi.fn();
  const restoreFocus = vi.fn();
  const result = render(
    <ToastProvider>
      <FeedbackDialog onClose={onClose} restoreFocus={restoreFocus} />
    </ToastProvider>,
  );
  return { ...result, onClose, restoreFocus };
}

function fillForm() {
  fireEvent.change(screen.getByLabelText("标题"), { target: { value: "页面无法加载" } });
  fireEvent.change(screen.getByLabelText("内容"), { target: { value: "点击后页面没有变化。" } });
}

describe("FeedbackDialog", () => {
  it("focuses the title on open, locks background scrolling, and restores focus on close", async () => {
    const priorOverflow = document.body.style.overflow;
    const { onClose, restoreFocus, unmount } = renderDialog();
    const title = screen.getByLabelText("标题");

    expect(title).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
    await waitFor(() => expect(restoreFocus).toHaveBeenCalledOnce());
    unmount();
    expect(document.body.style.overflow).toBe(priorOverflow);
  });

  it("shows character counts and validation errors for blank fields", () => {
    renderDialog();

    expect(screen.getByText("0 / 100")).toBeInTheDocument();
    expect(screen.getByText("0 / 2000")).toBeInTheDocument();
    fireEvent.submit(screen.getByRole("button", { name: "提交" }).closest("form")!);

    expect(screen.getByText("请输入反馈标题。")).toBeInTheDocument();
    expect(screen.getByText("请输入反馈内容。")).toBeInTheDocument();
    expect(screen.getByLabelText("标题")).toHaveAttribute("aria-invalid", "true");
  });

  it("submits the feedback and closes after success", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ message: "反馈提交成功" }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const { onClose } = renderDialog();
    fillForm();

    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/feedback",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ title: "页面无法加载", content: "点击后页面没有变化。" }),
      }),
    );
    expect(screen.getByText("反馈提交成功，感谢你的支持！")).toBeInTheDocument();
  });

  it("keeps the form open and preserves content after an API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: "服务暂不可用" }), { status: 503 }),
        ),
    );
    const { onClose } = renderDialog();
    fillForm();

    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("反馈提交失败，请稍后重试");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("标题")).toHaveValue("页面无法加载");
    expect(screen.getByLabelText("内容")).toHaveValue("点击后页面没有变化。");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows loading and blocks duplicate submission and dismissal while pending", async () => {
    let resolveFetch!: (response: Response) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { onClose } = renderDialog();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "提交" }));

    expect(screen.getByRole("button", { name: "提交中..." })).toBeDisabled();
    fireEvent.submit(screen.getByRole("dialog").querySelector("form")!);
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(onClose).not.toHaveBeenCalled();

    resolveFetch(new Response(JSON.stringify({ message: "反馈提交成功" }), { status: 200 }));
    await waitFor(() => expect(onClose).toHaveBeenCalledOnce());
  });
});
