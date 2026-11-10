import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { DigitalHumanConversation } from "./DigitalHumanConversation";

afterEach(cleanup);

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

it("收到完整K线流事件后绘制图表及前复权信息", () => {
  render(
    <DigitalHumanConversation
      messages={[]}
      pendingMessage={null}
      pendingQuestionMessageId={null}
      currentQuestionIndex={0}
      selectedAnswers={{}}
      streamedAssistantText="近几日走势向上。"
      streamedKlineChart={{
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
      }}
      onQuestionAnswerSelect={vi.fn()}
      onQuestionNext={vi.fn()}
      onQuestionPrevious={vi.fn()}
      onQuestionSubmit={vi.fn()}
      isSubmitting={false}
      isLoading={false}
    />,
  );

  expect(screen.getByRole("img", { name: /贵州茅台 日K K线图/ })).toBeInTheDocument();
  expect(screen.getByText("日K · 前复权")).toBeInTheDocument();
  expect(screen.getByText("数据来源：东方财富（通过 AKShare）")).toBeInTheDocument();
});
