import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DigitalHumanComposer } from "./DigitalHumanComposer";

describe("DigitalHumanComposer", () => {
  it("回复完成后将焦点恢复到输入框", () => {
    const props = {
      draft: "你好",
      disabled: false,
      recorderStatus: "idle" as const,
      onDraftChange: vi.fn(),
      onSend: vi.fn(),
      onToggleRecording: vi.fn(),
    };
    const { rerender } = render(<DigitalHumanComposer {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    rerender(<DigitalHumanComposer {...props} disabled />);
    rerender(<DigitalHumanComposer {...props} disabled={false} draft="" />);
    expect(screen.getByRole("textbox")).toHaveFocus();
  });
});
