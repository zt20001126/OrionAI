import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DigitalHumanPage } from "./DigitalHumanPage";
import { streamDigitalHumanReply } from "../conversations/conversationApi";

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }));
vi.mock("../../components/ToastProvider", () => ({ useToast: () => ({ showToast }) }));
vi.mock("../conversations/conversationApi", () => ({
  createConversation: vi.fn(),
  listAllMessages: vi.fn().mockResolvedValue({ skill_code: "digital_human", items: [] }),
  streamDigitalHumanReply: vi.fn(),
}));
vi.mock("./components/DigitalHumanAvatarHost", () => ({ DigitalHumanAvatarHost: () => null }));
vi.mock("./components/DigitalHumanInteractionHint", () => ({
  DigitalHumanInteractionHint: () => null,
}));
vi.mock("./hooks/useAssistantAudio", () => ({
  useAssistantAudio: () => ({
    audioRef: { current: null },
    isSpeaking: false,
    enqueueAudio: vi.fn(),
    stopAudio: stopAudio,
  }),
}));
vi.mock("./hooks/useMicrophoneRecorder", () => ({
  useMicrophoneRecorder: () => ({
    status: "idle",
    stopRecording: vi.fn(),
    startRecording: vi.fn(),
  }),
}));
const stopAudio = vi.fn();
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("数字人消息发送", () => {
  it("提交后立即清空输入框，等待回复时仍显示已发送的消息", async () => {
    vi.mocked(streamDigitalHumanReply).mockReturnValue(new Promise(() => {}));
    render(<DigitalHumanPage conversationId="conversation-1" onNavigate={vi.fn()} />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    expect(input).toHaveValue("");
    expect(screen.getByText("你好")).toBeInTheDocument();
    await waitFor(() => expect(streamDigitalHumanReply).toHaveBeenCalled());
  });

  it("发送失败后恢复草稿，方便用户重试", async () => {
    vi.mocked(streamDigitalHumanReply).mockRejectedValue(new Error("网络错误"));
    render(<DigitalHumanPage conversationId="conversation-1" onNavigate={vi.fn()} />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "需要重试" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(input).toHaveValue("需要重试"));
  });
});
