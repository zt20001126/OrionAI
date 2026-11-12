import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import type {
  ConversationMessage,
  KlineChartPayload,
  RouteResult,
} from "../../conversations/conversationApi";
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
                      image_url: "https://example.com/store.jpg",
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
  expect(screen.getByRole("img", { name: "评分 4.6" })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "一点点（文一西路店）商家图片" })).toHaveAttribute(
    "src",
    "https://example.com/store.jpg",
  );
  expect(screen.getByRole("link", { name: "0571-88881234" })).toHaveAttribute(
    "href",
    "tel:0571-88881234",
  );
  expect(screen.getByText("约 430 米")).toBeInTheDocument();
  expect(screen.getByText("营业 09:00-22:00")).toBeInTheDocument();
  expect(screen.getByText("查看位置")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "在高德地图中查看一点点（文一西路店）" }),
  ).toHaveAttribute(
    "href",
    `https://uri.amap.com/search?keyword=${encodeURIComponent("一点点（文一西路店） 杭州市西湖区文一西路369号")}&view=map`,
  );
  expect(screen.queryByText("地图位置")).not.toBeInTheDocument();
});

it("商家图片缺失或加载失败时展示店铺图标，无电话时显示提示", () => {
  const message: ConversationMessage = {
    id: "place-fallback-message",
    conversation_id: "2",
    role: "assistant",
    created_at: "2026-11-06T00:00:00Z",
    content: {
      parts: [
        {
          type: "place_cards",
          data: {
            title: "附近的餐厅",
            total: 2,
            places: [
              {
                id: "poi-no-image",
                name: "无图片餐厅",
                address: "杭州市西湖区文一西路 1 号",
                distance: 1250,
                tel: null,
                business_hours: null,
                rating: null,
                image_url: null,
              },
              {
                id: "poi-broken-image",
                name: "图片加载失败餐厅",
                address: "杭州市西湖区文一西路 2 号",
                distance: 800,
                tel: "057188881234",
                business_hours: "09:00-22:00",
                rating: 4.2,
                image_url: "https://example.com/broken.jpg",
              },
            ],
          },
        },
      ],
    },
  };
  renderConversation(null, [message]);

  expect(screen.getByText("约 1.3 公里")).toBeInTheDocument();
  expect(screen.getByText("暂无电话")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "暂无电话" })).not.toBeInTheDocument();
  expect(screen.getByRole("img", { name: "无图片餐厅商家图片" })).toHaveClass(
    "digital-human-place-card__image-fallback",
  );

  fireEvent.error(screen.getByRole("img", { name: "图片加载失败餐厅商家图片" }));
  expect(screen.getByRole("img", { name: "图片加载失败餐厅商家图片" })).toHaveClass(
    "digital-human-place-card__image-fallback",
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

const routeModes: {
  mode: RouteResult["mode"];
  label: string;
  navigationMode: string;
}[] = [
  { mode: "walking", label: "步行", navigationMode: "walk" },
  { mode: "cycling", label: "骑行", navigationMode: "ride" },
  { mode: "driving", label: "驾车", navigationMode: "car" },
];

it.each(routeModes)("展示$label路线及对应导航链接", ({ mode, label, navigationMode }) => {
  const onPlanRoute = vi.fn();
  const place = {
    id: "poi-1",
    name: "商店",
    address: "西湖区",
    location: "120.16,30.29",
    distance: 200,
    tel: null,
    business_hours: null,
    rating: null,
    image_url: null,
  };
  const messages: ConversationMessage[] = [
    {
      id: "1",
      conversation_id: "2",
      role: "assistant",
      created_at: "2026-11-06T00:00:00Z",
      content: {
        parts: [{ type: "place_cards", data: { title: "附近商家", total: 1, places: [place] } }],
      },
    },
    {
      id: "2",
      conversation_id: "2",
      role: "assistant",
      created_at: "2026-11-06T00:00:00Z",
      content: {
        parts: [
          {
            type: "route_result",
            data: {
              mode,
              origin: { name: "我的位置", location: "120.15,30.28" },
              destination: { name: "商店", location: "120.16,30.29" },
              distance_m: 1050,
              duration_s: 780,
              steps: [{ instruction: "向东走", distance_m: 300, polyline: null }],
            },
          },
        ],
      },
    },
  ];
  render(
    <DigitalHumanConversation
      messages={messages}
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
      onPlanRoute={onPlanRoute}
      isSubmitting={false}
      isLoading={false}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "路线规划" }));
  expect(onPlanRoute).toHaveBeenCalledWith(place);
  expect(screen.getByRole("heading", { name: `${label}路线` })).toBeInTheDocument();
  expect(screen.getByText("向东走")).toBeInTheDocument();
  expect(screen.getByText("1.05 公里")).toBeInTheDocument();
  const link = new URL(screen.getByRole("link", { name: "开始导航" }).getAttribute("href")!);
  expect(link.pathname).toBe("/navigation");
  expect(link.searchParams.get("from")).toBe("120.15,30.28,我的位置");
  expect(link.searchParams.get("to")).toBe("120.16,30.29,商店");
  expect(link.searchParams.get("mode")).toBe(navigationMode);
});
