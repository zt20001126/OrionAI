import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DigitalHumanPage } from "./DigitalHumanPage";
import {
  listAllMessages,
  planPlaceRoute,
  streamDigitalHumanReply,
  type ConversationMessage,
  type PlaceCard,
} from "../conversations/conversationApi";
import { requestBrowserLocation } from "../conversations/browserLocation";

const { showToast, enqueueAudio, stopAudio } = vi.hoisted(() => ({
  showToast: vi.fn(),
  enqueueAudio: vi.fn(),
  stopAudio: vi.fn(),
}));
vi.mock("../../components/ToastProvider", () => ({ useToast: () => ({ showToast }) }));
vi.mock("../conversations/conversationApi", () => ({
  createConversation: vi.fn(),
  listAllMessages: vi.fn().mockResolvedValue({ skill_code: "digital_human", items: [] }),
  planPlaceRoute: vi.fn(),
  streamDigitalHumanReply: vi.fn(),
}));
vi.mock("../conversations/browserLocation", () => ({
  requestBrowserLocation: vi.fn().mockResolvedValue({
    status: "granted",
    latitude: 30.28,
    longitude: 120.15,
    accuracy_meters: 10,
  }),
}));
vi.mock("./components/DigitalHumanAvatarHost", () => ({ DigitalHumanAvatarHost: () => null }));
vi.mock("./components/DigitalHumanInteractionHint", () => ({
  DigitalHumanInteractionHint: () => null,
}));
vi.mock("./hooks/useAssistantAudio", () => ({
  useAssistantAudio: () => ({
    audioRef: { current: null },
    isSpeaking: false,
    enqueueAudio,
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
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe("数字人消息发送", () => {
  it("默认开启并将用户切换后的选择保存到 localStorage", () => {
    const firstRender = render(<DigitalHumanPage conversationId={null} onNavigate={vi.fn()} />);
    const toggle = screen.getByRole("switch", { name: "关闭语音播报" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    fireEvent.click(toggle);
    expect(window.localStorage.getItem("orionai:digital-human:voice-enabled")).toBe("false");
    firstRender.unmount();

    render(<DigitalHumanPage conversationId={null} onNavigate={vi.fn()} />);
    expect(screen.getByRole("switch", { name: "开启语音播报" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

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

  it("关闭后刷新仍保持关闭，并以 voice=false 请求文字回复", async () => {
    window.localStorage.setItem("orionai:digital-human:voice-enabled", "false");
    vi.mocked(streamDigitalHumanReply).mockReturnValue(new Promise(() => {}));
    render(<DigitalHumanPage conversationId="conversation-1" onNavigate={vi.fn()} />);

    expect(screen.getByRole("switch", { name: "开启语音播报" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "只要文字" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => expect(streamDigitalHumanReply).toHaveBeenCalled());
    expect(vi.mocked(streamDigitalHumanReply).mock.calls[0]?.[8]).toBe(false);
  });

  it("切换开关只影响后续回复，不打断当前播报", async () => {
    vi.mocked(streamDigitalHumanReply).mockReturnValue(new Promise(() => {}));
    render(<DigitalHumanPage conversationId="conversation-1" onNavigate={vi.fn()} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "当前回复继续播报" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(streamDigitalHumanReply).toHaveBeenCalled());

    const onAudio = vi.mocked(streamDigitalHumanReply).mock.calls[0]?.[4];
    expect(vi.mocked(streamDigitalHumanReply).mock.calls[0]?.[8]).toBe(true);
    stopAudio.mockClear();
    fireEvent.click(screen.getByRole("switch", { name: "关闭语音播报" }));
    expect(window.localStorage.getItem("orionai:digital-human:voice-enabled")).toBe("false");
    expect(stopAudio).not.toHaveBeenCalled();
    onAudio?.({
      type: "audio_segment",
      turn_id: "current-turn",
      segment_id: 1,
      audio: "YXVkaW8=",
    });

    expect(enqueueAudio).toHaveBeenCalledOnce();
    expect(screen.getByRole("switch", { name: "开启语音播报" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });
});

describe("数字人能力引导", () => {
  it("点击能力只填入提示词，支持切换且不自动发送", () => {
    render(<DigitalHumanPage conversationId={null} onNavigate={vi.fn()} />);
    const input = screen.getByRole("textbox");
    fireEvent.click(screen.getByRole("button", { name: /生成图片/ }));
    expect(input).toHaveValue("帮我生成一张图片");
    const suggestions = document.querySelectorAll(".digital-human-welcome__item");
    expect(suggestions).toHaveLength(14);
    expect(suggestions[4]).toHaveTextContent("简历修改");
    expect(suggestions[5]).toHaveTextContent("生成视频");
    expect(suggestions[6]).toHaveTextContent("查询文献");
    expect(suggestions[7]).toHaveTextContent("查询天气");
    expect(suggestions[10]).toHaveTextContent("查询附近的奶茶店");
    expect(suggestions[10]).toHaveTextContent("帮我查找附近的奶茶店");
    expect(suggestions[11]).toHaveTextContent("查询002086的K线图");
    expect(suggestions[12]).toHaveTextContent("互动聊天");
    expect(suggestions[13]).toHaveTextContent("了解我的能力");
    fireEvent.click(screen.getByRole("button", { name: /查询附近的奶茶店/ }));
    expect(input).toHaveValue("帮我查询附近的奶茶店");
    fireEvent.click(screen.getByRole("button", { name: /查询002086的K线图/ }));
    expect(input).toHaveValue("帮我查询股票002086的K线图");
    fireEvent.click(screen.getByRole("button", { name: /简历修改/ }));
    expect(input).toHaveValue("帮我修改求职意向");
    fireEvent.click(screen.getByRole("button", { name: /生成视频/ }));
    expect(input).toHaveValue("帮我生成一个视频");
    fireEvent.click(screen.getByRole("button", { name: /了解我的能力/ }));
    expect(input).toHaveValue("你都有哪些能力？");
    fireEvent.click(screen.getByRole("button", { name: /查询文献/ }));
    expect(input).toHaveValue("帮我查找关于目标检测的文献");
    fireEvent.click(screen.getByRole("button", { name: /查询天气/ }));
    expect(input).toHaveValue("帮我查一下北京今天的天气");
    expect(streamDigitalHumanReply).not.toHaveBeenCalled();
  });

  it("每次进入新会话均显示，历史会话保留消息区域", () => {
    const { unmount } = render(<DigitalHumanPage conversationId={null} onNavigate={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "跳过引导" }));
    expect(screen.queryByText("跳过引导")).not.toBeInTheDocument();
    unmount();
    const { rerender } = render(<DigitalHumanPage conversationId={null} onNavigate={vi.fn()} />);
    expect(screen.getByText("跳过引导")).toBeInTheDocument();
    rerender(<DigitalHumanPage conversationId="conversation-1" onNavigate={vi.fn()} />);
    expect(screen.queryByText("跳过引导")).not.toBeInTheDocument();
    rerender(<DigitalHumanPage conversationId={null} onNavigate={vi.fn()} />);
    expect(screen.getByText("跳过引导")).toBeInTheDocument();
  });
});

describe("商家路线方式选择", () => {
  it("点击商家路线规划后先询问方式，再用该商家坐标请求骑行路线", async () => {
    const place: PlaceCard = {
      id: "poi-1",
      name: "西湖咖啡店",
      address: "杭州市西湖区文一西路 1 号",
      distance: 300,
      tel: null,
      business_hours: null,
      rating: null,
      image_url: null,
      location: "120.16,30.29",
    };
    const placeMessage: ConversationMessage = {
      id: "places-1",
      conversation_id: "conversation-1",
      role: "assistant",
      created_at: "2026-11-12T00:00:00Z",
      content: {
        parts: [{ type: "place_cards", data: { title: "附近商家", total: 1, places: [place] } }],
      },
    };
    vi.mocked(listAllMessages).mockResolvedValue({
      skill_code: "digital_human",
      items: [placeMessage],
      limit: 100,
      offset: 0,
    });
    vi.mocked(planPlaceRoute).mockResolvedValueOnce({
      ...placeMessage,
      id: "route-1",
      content: {
        parts: [
          {
            type: "route_result",
            data: {
              mode: "cycling",
              origin: { name: "我的位置", location: "120.15,30.28" },
              destination: { name: place.name, location: place.location! },
              distance_m: 1200,
              duration_s: 600,
              steps: [],
            },
          },
        ],
      },
    });

    render(<DigitalHumanPage conversationId="conversation-1" onNavigate={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "路线规划" }));

    expect(screen.getByRole("article", { name: "路线方式选择" })).toBeInTheDocument();
    expect(requestBrowserLocation).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("radio", { name: /骑行/ }));
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));

    await waitFor(() =>
      expect(planPlaceRoute).toHaveBeenCalledWith(
        "conversation-1",
        place,
        {
          status: "granted",
          latitude: 30.28,
          longitude: 120.15,
          accuracy_meters: 10,
        },
        "cycling",
        expect.any(String),
      ),
    );
  });
});
