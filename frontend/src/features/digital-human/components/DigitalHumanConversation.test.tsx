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
