import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type { ConversationMessage, KlineChartPayload } from "../../conversations/conversationApi";
import { DigitalHumanConversation } from "./DigitalHumanConversation";

afterEach(cleanup);

const chart: KlineChartPayload = {
  code: "600519",
  name: "贵州茅台",
  period: "daily",
  adjust: "qfq",
  start_date: "2026-11-09",
  end_date: "2026-11-10",
  source: "东方财富（通过 AKShare）",
  candles: [
    {
      date: "2026-11-09",
      open: 1400,
      close: 1410,
      high: 1420,
      low: 1390,
      volume: 1000,
    },
    {
      date: "2026-11-10",
      open: 1410,
      close: 1405,
      high: 1425,
      low: 1400,
      volume: 1200,
    },
  ],
};

function renderConversation(
  streamedKlineChart: KlineChartPayload | null,
  messages: ConversationMessage[] = [],
) {
  return render(
    <DigitalHumanConversation
      messages={messages}
      pendingMessage={null}
      pendingQuestionMessageId={null}
      currentQuestionIndex={0}
      selectedAnswers={{}}
      streamedAssistantText={streamedKlineChart ? "近几日走势向上。" : ""}
      streamedKlineChart={streamedKlineChart}
      streamedPlaceCards={null}
      onQuestionAnswerSelect={vi.fn()}
      onQuestionNext={vi.fn()}
      onQuestionPrevious={vi.fn()}
      onQuestionSubmit={vi.fn()}
      isSubmitting={false}
      isLoading={false}
    />,
  );
}

it("在历史消息中显示私有视频并提示播放错误", () => {
  render(
    <DigitalHumanConversation
      messages={[
        {
          id: "1",
          conversation_id: "2",
          role: "assistant",
          created_at: "2026-11-06T00:00:00Z",
          content: {
            parts: [
              { type: "text", text: "视频已生成" },
              {
                type: "video_result",
                task_result_id: "123",
                generation_status: "succeeded",
                video_url: "/api/digital-human/task-results/123/video",
              },
            ],
          },
        },
      ]}
      pendingMessage={null}
      pendingQuestionMessageId={null}
      currentQuestionIndex={0}
      selectedAnswers={{}}
      streamedAssistantText=""
      streamedKlineChart={null}
      streamedPlaceCards={null}
      onQuestionAnswerSelect={vi.fn()}
      onQuestionNext={vi.fn()}
      onQuestionPrevious={vi.fn()}
      onQuestionSubmit={vi.fn()}
      isSubmitting={false}
      isLoading={false}
    />,
  );
  const video = screen.getByLabelText("AI 生成的视频");
  expect(video).toHaveAttribute("src", "/api/digital-human/task-results/123/video");
  expect(video).toHaveAttribute("controls");
  fireEvent.error(video);
  expect(screen.getByText("生成视频暂时无法播放。")).toBeInTheDocument();
});

it("收到完整K线流事件和MA数据后绘制均线及前复权信息", () => {
  renderConversation({
    ...chart,
    moving_averages: [{ period: 5, values: [1402, 1408] }],
  });

  expect(screen.getByRole("img", { name: /贵州茅台 日K K线图/ })).toBeInTheDocument();
  expect(screen.getByText("日K · 前复权")).toBeInTheDocument();
  expect(screen.getByText("数据来源：东方财富（通过 AKShare）")).toBeInTheDocument();
  expect(screen.getByText("MA5")).toBeInTheDocument();
  expect(document.querySelector(".digital-human-kline__moving-average--5")).toBeInTheDocument();
});

it("在历史消息中以卡片展示周边商家资料", () => {
  render(
    <DigitalHumanConversation
      messages={[
        {
          id: "place-message",
          conversation_id: "2",
          role: "assistant",
          created_at: "2026-11-06T00:00:00Z",
          content: {
            parts: [
              {
                type: "place_cards",
                data: {
                  title: "附近的奶茶店",
                  total: 1,
                  places: [
                    {
                      id: "poi-1",
                      name: "一点点（文一西路店）",
                      address: "杭州市西湖区文一西路369号",
                      distance: 430,
                      tel: "0571-88881234",
                      business_hours: "09:00-22:00",
                      rating: 4.6,
                    },
                  ],
                },
              },
            ],
          },
        },
      ]}
      pendingMessage={null}
      pendingQuestionMessageId={null}
      currentQuestionIndex={0}
      selectedAnswers={{}}
      streamedAssistantText=""
      streamedKlineChart={null}
      streamedPlaceCards={null}
      onQuestionAnswerSelect={vi.fn()}
      onQuestionNext={vi.fn()}
      onQuestionPrevious={vi.fn()}
      onQuestionSubmit={vi.fn()}
      isSubmitting={false}
      isLoading={false}
    />,
  );

  expect(screen.getByRole("region", { name: "附近的奶茶店" })).toBeInTheDocument();
  expect(screen.getByText("一点点（文一西路店）")).toBeInTheDocument();
  expect(screen.getByText("★ 4.6")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "0571-88881234" })).toHaveAttribute(
    "href",
    "tel:0571-88881234",
  );
});

it("没有请求MA时只显示蜡烛图", () => {
  renderConversation(chart);

  expect(screen.getByRole("img", { name: /贵州茅台 日K K线图/ })).toBeInTheDocument();
  expect(screen.queryByText(/^MA\d+$/)).not.toBeInTheDocument();
  expect(document.querySelector(".digital-human-kline__moving-average")).not.toBeInTheDocument();
});

it("历史消息中的K线保留并绘制MA曲线", () => {
  renderConversation(null, [
    {
      id: "assistant-1",
      conversation_id: "conversation-1",
      role: "assistant",
      created_at: "2026-11-10T00:00:00Z",
      content: {
        parts: [
          {
            type: "kline_chart",
            content: { ...chart, moving_averages: [{ period: 20, values: [1402, 1408] }] },
          },
        ],
      },
    },
  ]);

  expect(screen.getByText("MA20")).toBeInTheDocument();
  expect(document.querySelector(".digital-human-kline__moving-average--20")).toBeInTheDocument();
});
