import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { VoiceRecordingOverlay } from "./VoiceRecordingOverlay";

describe("VoiceRecordingOverlay", () => {
  it("仅在录音时响应 Escape 和取消按钮", () => {
    const onCancel = vi.fn();
    const { rerender, unmount } = render(<VoiceRecordingOverlay isRecording onCancel={onCancel} />);
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "取消录音" }));
    expect(onCancel).toHaveBeenCalledTimes(2);
    rerender(<VoiceRecordingOverlay isRecording={false} onCancel={onCancel} />);
    fireEvent.keyDown(window, { key: "Escape" });
    unmount();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledTimes(2);
  });
});
