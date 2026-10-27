import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/app/App";
import type {
  ConversationMessage,
  ConversationSummary,
  QuestionContentPart,
} from "../src/features/conversations/conversationApi";

const createdConversationId = "9007199254740993";
const createdAt = "2026-10-26T08:00:00Z";

function textMessage(
  id: string,
  conversationId: string,
  role: "user" | "assistant",
  text: string,
): ConversationMessage {
  return {
    id,
    conversation_id: conversationId,
    role,
    content: { parts: [{ type: "text", text }] },
    created_at: createdAt,
  };
}

function singleChoiceQuestion(
  id: string,
  title: string,
  labels: string[],
): QuestionContentPart["questions"][number] {
  return {
    id,
    title,
    type: "SingleChoice",
    allow_custom_input: false,
    options: labels.map((label) => ({ label, description: `${label}选项。` })),
  };
}

function getQuestionPartForTest(
  message: ConversationMessage | undefined,
): QuestionContentPart | null {
  if (message?.role !== "assistant") return null;

  return (
    message.content.parts.find((part): part is QuestionContentPart => part.type === "question") ??
    null
  );
}

function createBackend(options?: {
  conversations?: ConversationSummary[];
  messages?: Record<string, ConversationMessage[]>;
}) {
  const conversations = [...(options?.conversations ?? [])];
  const messages = new Map<string, ConversationMessage[]>(
    Object.entries(options?.messages ?? {}).map(([id, items]) => [id, [...items]]),
  );
  const calls: Array<{ url: URL; method: string; body: Record<string, unknown> | null }> = [];
  let nextMessageId = 100;

  const fetchMock = vi
    .fn()
    .mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      const method = init?.method ?? "GET";
      const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
      calls.push({ url, method, body });

      if (url.pathname === "/api/auth/session") {
        return {
          ok: true,
          status: 200,
          json: async () => ({ authenticated: true, account: "person@example.com" }),
        } as Response;
      }

      if (url.pathname === "/api/v1/users/me/skills" && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: [
              {
                id: "373284764594991100",
                code: "general_chat",
                name: "通用对话助手",
                description: "支持日常问答和多轮对话",
                type: "agent",
                status: "published",
                created_at: createdAt,
                added_at: createdAt,
                is_added: true,
              },
            ],
          }),
        } as Response;
      }

      if (url.pathname === "/api/conversations" && method === "POST") {
        const conversation: ConversationSummary = {
          id: createdConversationId,
          title: null,
          created_at: createdAt,
          updated_at: createdAt,
        };
        conversations.unshift(conversation);
        messages.set(conversation.id, []);
        return { ok: true, status: 201, json: async () => conversation } as Response;
      }

      if (url.pathname === "/api/conversations" && method === "GET") {
        const limit = Number(url.searchParams.get("limit") ?? 50);
        const offset = Number(url.searchParams.get("offset") ?? 0);
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: conversations.slice(offset, offset + limit), limit, offset }),
        } as Response;
      }

      const messageRoute = url.pathname.match(/^\/api\/conversations\/([^/]+)\/messages$/);
      if (messageRoute && method === "GET") {
        const conversationId = messageRoute[1];
        const items = messages.get(conversationId) ?? [];
        const limit = Number(url.searchParams.get("limit") ?? 50);
        const offset = Number(url.searchParams.get("offset") ?? 0);
        return {
          ok: true,
          status: 200,
          json: async () => ({ items: items.slice(offset, offset + limit), limit, offset }),
        } as Response;
      }

      if (messageRoute && method === "POST") {
        const conversationId = messageRoute[1];
        const items = messages.get(conversationId) ?? [];
        const userText = typeof body?.message === "string" ? body.message : "";
        items.push(textMessage(String(nextMessageId++), conversationId, "user", userText));
        const questions: QuestionContentPart["questions"] | null =
          userText === "请先问我一个选择题"
            ? [
                singleChoiceQuestion("response_style", "你希望回答采用哪种风格？", [
                  "简洁",
                  "详细",
                  "正式",
                  "轻松",
                ]),
              ]
            : userText === "请发我三道题"
              ? [
                  singleChoiceQuestion("main_issue", "你目前遇到的主要问题是什么？", [
                    "选择一",
                    "选择二",
                    "选择三",
                    "选择四",
                  ]),
                  singleChoiceQuestion("experience", "你目前的工作年限是多少？", [
                    "1 年内",
                    "1–3 年",
                    "3–8 年",
                    "8 年以上",
                  ]),
                  singleChoiceQuestion("priority", "你最看重工作的哪一方面？", [
                    "薪资待遇",
                    "技术成长",
                    "工作稳定性",
                    "工作内容",
                  ]),
                ]
              : null;
        const assistantMessage = questions
          ? {
              id: String(nextMessageId++),
              conversation_id: conversationId,
              role: "assistant" as const,
              content: { parts: [{ type: "question" as const, questions }] },
              created_at: createdAt,
            }
          : textMessage(
              String(nextMessageId++),
              conversationId,
              "assistant",
              `已回答：${userText}`,
            );
        items.push(assistantMessage);
        messages.set(conversationId, items);
        const conversation = conversations.find((item) => item.id === conversationId);
        if (conversation) {
          conversation.updated_at = createdAt;
          if (!conversation.title && items.filter((item) => item.role === "user").length === 1) {
            conversation.title = "首条消息自动标题";
          }
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            status:
              assistantMessage.content.parts[0]?.type === "question" ? "waiting" : "completed",
            message: assistantMessage,
          }),
        } as Response;
      }

      const answersRoute = url.pathname.match(/^\/api\/conversations\/([^/]+)\/answers$/);
      if (answersRoute && method === "POST") {
        const conversationId = answersRoute[1];
        const items = messages.get(conversationId) ?? [];
        const answers =
          body?.answers && typeof body.answers === "object" && !Array.isArray(body.answers)
            ? (body.answers as Record<string, unknown>)
            : {};
        const latestQuestion = getQuestionPartForTest(items.at(-1));
        const answerText = latestQuestion
          ? `用户已提交以下选择：\n${latestQuestion.questions
              .map((question) => `- ${question.title}：${String(answers[question.id] ?? "")}`)
              .join("\n")}`
          : "用户已提交以下选择：";
        items.push(textMessage(String(nextMessageId++), conversationId, "user", answerText));
        const assistantMessage = textMessage(
          String(nextMessageId++),
          conversationId,
          "assistant",
          "已按选择继续对话。",
        );
        items.push(assistantMessage);
        messages.set(conversationId, items);
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: "completed", message: assistantMessage }),
        } as Response;
      }

      return { ok: false, status: 404, json: async () => ({ detail: "未找到请求。" }) } as Response;
    });

  return { calls, fetchMock };
}

beforeEach(() => {
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("OrionAI conversations", () => {
  it("creates a conversation on first send and continues multi-turn messages with the string ID", async () => {
    window.history.replaceState({}, "", "/agents");
    const backend = createBackend();
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "使用" }));
    expect(await screen.findByText("有什么问题，尽管问我。")).toBeInTheDocument();

    const messageInput = screen.getByRole("textbox", { name: "发送消息" });
    fireEvent.change(messageInput, {
      target: { value: "你好" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText("已回答：你好")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /首条消息自动标题/ })).toBeInTheDocument();
    expect(messageInput).toHaveFocus();
    expect(window.location.pathname).toBe(`/chat/${createdConversationId}`);
    expect(
      backend.calls.some(
        ({ url, method }) => url.pathname === "/api/conversations" && method === "POST",
      ),
    ).toBe(true);
    expect(
      backend.calls.some(
        ({ url, method, body }) =>
          url.pathname === `/api/conversations/${createdConversationId}/messages` &&
          method === "POST" &&
          body?.message === "你好",
      ),
    ).toBe(true);

    fireEvent.change(screen.getByRole("textbox", { name: "发送消息" }), {
      target: { value: "再问一个问题" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    expect(await screen.findByText("已回答：再问一个问题")).toBeInTheDocument();
    expect(messageInput).toHaveFocus();
    expect(window.location.pathname).toBe(`/chat/${createdConversationId}`);
  });

  it("submits every required question answer and resumes the same conversation", async () => {
    window.history.replaceState({}, "", "/chat");
    const backend = createBackend();
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole("textbox", { name: "发送消息" }), {
      target: { value: "请先问我一个选择题" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    const option = await screen.findByRole("radio", { name: /简洁/ });
    expect(screen.getByRole("button", { name: "发送消息" })).toBeDisabled();
    fireEvent.click(option);
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByText("已按选择继续对话。")).toBeInTheDocument();
    expect(screen.getByText(/已提交回答 · 共 1 题/)).toBeInTheDocument();
    expect(screen.getByText("简洁", { selector: "strong" })).toBeInTheDocument();
    expect(
      document.querySelector(".conversation-message--user .conversation-message__label"),
    ).toBeNull();
    expect(
      backend.calls.some(
        ({ url, method, body }) =>
          url.pathname === `/api/conversations/${createdConversationId}/answers` &&
          method === "POST" &&
          typeof body?.answers === "object" &&
          body.answers !== null &&
          "response_style" in body.answers &&
          body.answers.response_style === "简洁",
      ),
    ).toBe(true);
  });

  it("retains a selected answer when submission fails and allows retry", async () => {
    window.history.replaceState({}, "", "/chat");
    const backend = createBackend();
    const originalFetch = backend.fetchMock.getMockImplementation();
    if (!originalFetch) throw new Error("对话接口 mock 未初始化。");
    let failNextAnswer = true;
    backend.fetchMock.mockImplementation(async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (failNextAnswer && url.pathname.endsWith("/answers") && init?.method === "POST") {
        failNextAnswer = false;
        return {
          ok: false,
          status: 503,
          json: async () => ({ detail: "题目服务暂不可用。" }),
        } as Response;
      }
      return originalFetch(input, init);
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole("textbox", { name: "发送消息" }), {
      target: { value: "请先问我一个选择题" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    const option = await screen.findByRole("radio", { name: /简洁/ });
    fireEvent.click(option);
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("题目服务暂不可用。");
    expect(screen.getByRole("radio", { name: /简洁/ })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByText(/已提交回答 · 共 1 题/)).toBeInTheDocument();
  });

  it("walks through a multi-question card and submits retained answers once", async () => {
    window.history.replaceState({}, "", "/chat");
    const backend = createBackend();
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole("textbox", { name: "发送消息" }), {
      target: { value: "请发我三道题" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText("你目前遇到的主要问题是什么？")).toBeInTheDocument();
    expect(screen.queryByText("你目前的工作年限是多少？")).not.toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "答题进度" })).toHaveAttribute(
      "aria-valuenow",
      "1",
    );

    fireEvent.click(screen.getByRole("radio", { name: /选择一/ }));
    fireEvent.click(screen.getByRole("button", { name: /下一题/ }));
    expect(screen.getByText("你目前的工作年限是多少？")).toBeInTheDocument();
    expect(screen.queryByText("你目前遇到的主要问题是什么？")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /1–3 年/ }));
    fireEvent.click(screen.getByRole("button", { name: /上一题/ }));
    expect(screen.getByRole("radio", { name: /选择一/ })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: /下一题/ }));
    fireEvent.click(screen.getByRole("button", { name: /下一题/ }));
    expect(screen.getByText("你最看重工作的哪一方面？")).toBeInTheDocument();
    expect(
      backend.calls.some(
        ({ method, url }) => method === "POST" && url.pathname.endsWith("/answers"),
      ),
    ).toBe(false);

    fireEvent.click(screen.getByRole("radio", { name: /技术成长/ }));
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByText("已按选择继续对话。")).toBeInTheDocument();
    expect(screen.getByText(/已提交回答 · 共 3 题/)).toBeInTheDocument();
    expect(screen.getByText("你目前遇到的主要问题是什么？")).toBeInTheDocument();
    expect(screen.getByText("选择一", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("1–3 年", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("技术成长", { selector: "strong" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交答案" })).not.toBeInTheDocument();

    const answerCall = backend.calls.find(
      ({ method, url }) => method === "POST" && url.pathname.endsWith("/answers"),
    );
    expect(answerCall?.body?.answers).toEqual({
      main_issue: "选择一",
      experience: "1–3 年",
      priority: "技术成长",
    });
  });

  it("keeps Shift+Enter in the draft and sends on Enter", async () => {
    window.history.replaceState({}, "", "/chat");
    const backend = createBackend();
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    const input = await screen.findByRole("textbox", { name: "发送消息" });
    fireEvent.change(input, { target: { value: "通过键盘发送" } });
    input.focus();
    fireEvent.keyDown(input, { key: "Enter", isComposing: true });
    fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });

    expect(input).toHaveValue("通过键盘发送");
    expect(
      backend.calls.some(
        ({ method, url }) => method === "POST" && url.pathname.endsWith("/messages"),
      ),
    ).toBe(false);

    fireEvent.keyDown(input, { key: "Enter" });
    expect(await screen.findByText("已回答：通过键盘发送")).toBeInTheDocument();
    expect(input).toHaveFocus();
  });

  it("follows new messages until the user scrolls up during a reply", async () => {
    const conversationId = "9100000000000003";
    window.history.replaceState({}, "", `/chat/${conversationId}`);
    const backend = createBackend({
      messages: {
        [conversationId]: [
          textMessage("204", conversationId, "user", "先前的问题"),
          textMessage("205", conversationId, "assistant", "先前的回答"),
        ],
      },
    });
    const originalFetch = backend.fetchMock.getMockImplementation();
    if (!originalFetch) throw new Error("对话接口 mock 未初始化。");
    let releaseMessageResponse!: () => void;
    const responseGate = new Promise<void>((resolve) => {
      releaseMessageResponse = resolve;
    });
    backend.fetchMock.mockImplementation(async (input, init) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname.endsWith("/messages") && init?.method === "POST") {
        await responseGate;
      }
      return originalFetch(input, init);
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    await screen.findByRole("textbox", { name: "发送消息" });
    const messageLog = screen.getByRole("log", { name: "对话消息" });
    Object.defineProperties(messageLog, {
      clientHeight: { configurable: true, value: 400 },
      scrollHeight: { configurable: true, value: 1200 },
    });
    let scrollTop = 0;
    Object.defineProperty(messageLog, "scrollTop", {
      configurable: true,
      get: () => scrollTop,
      set: (value: number) => {
        scrollTop = Math.min(value, 800);
      },
    });

    fireEvent.change(screen.getByRole("textbox", { name: "发送消息" }), {
      target: { value: "继续追问" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    expect(await screen.findByText("助手正在回复…")).toBeInTheDocument();
    expect(messageLog.scrollTop).toBe(800);

    messageLog.scrollTop = 350;
    fireEvent.scroll(messageLog);
    const profileButton = screen.getByRole("button", { name: "更多用户选项" });
    profileButton.focus();
    fireEvent.click(profileButton);
    releaseMessageResponse();

    expect(await screen.findByText("已回答：继续追问")).toBeInTheDocument();
    expect(messageLog.scrollTop).toBe(350);
    expect(profileButton).toHaveFocus();
  });

  it("renders assistant Markdown and GFM with links kept safe", async () => {
    const conversationId = "9100000000000002";
    window.history.replaceState({}, "", `/chat/${conversationId}`);
    const backend = createBackend({
      messages: {
        [conversationId]: [
          textMessage(
            "203",
            conversationId,
            "assistant",
            [
              "## 计划",
              "",
              "**清晰**的回答，包含 `inline code`。",
              "",
              "- 第一项",
              "- 第二项",
              "",
              "```ts",
              "const answer = true;",
              "```",
              "",
              "| 名称 | 状态 |",
              "| --- | --- |",
              "| 回复 | 完成 |",
              "",
              "[官方链接](https://example.com)",
              "[危险链接](javascript:alert%281%29)",
              "",
              "<img src=x onerror=alert(1)>",
            ].join("\n"),
          ),
        ],
      },
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "计划" })).toBeInTheDocument();
    expect(
      document.querySelector(".conversation-message__bubble .conversation-message__label"),
    ).toBeNull();
    expect(screen.getByText("清晰", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("inline code", { selector: "code" })).toBeInTheDocument();
    expect(screen.getByRole("list").querySelectorAll("li")).toHaveLength(2);
    expect(screen.getByText("const answer = true;", { selector: "code" })).toBeInTheDocument();
    expect(screen.getByRole("table").querySelectorAll("tr")).toHaveLength(2);

    const link = screen.getByRole("link", { name: "官方链接" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText("危险链接").closest("a")).toBeNull();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("opens a history conversation from the session page and restores its messages", async () => {
    const historyId = "9100000000000001";
    const existingConversation: ConversationSummary = {
      id: historyId,
      title: "季度规划讨论",
      created_at: createdAt,
      updated_at: createdAt,
    };
    window.history.replaceState({}, "", "/sessions");
    const backend = createBackend({
      conversations: [existingConversation],
      messages: {
        [historyId]: [
          textMessage("201", historyId, "user", "帮我整理季度目标"),
          textMessage("202", historyId, "assistant", "本季度目标分为三项。"),
        ],
      },
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: /季度规划讨论/ }));

    expect(await screen.findByText("本季度目标分为三项。")).toBeInTheDocument();
    expect(window.location.pathname).toBe(`/chat/${historyId}`);
  });

  it("restores a submitted question summary from historical messages", async () => {
    const conversationId = "9100000000000004";
    const questions: QuestionContentPart["questions"] = [
      singleChoiceQuestion("work_style", "你偏好的工作方式是什么？", [
        "独立完成",
        "团队协作",
        "灵活切换",
        "尚不确定",
      ]),
    ];
    const questionMessage: ConversationMessage = {
      id: "206",
      conversation_id: conversationId,
      role: "assistant",
      content: { parts: [{ type: "question", questions }] },
      created_at: createdAt,
    };
    window.history.replaceState({}, "", `/chat/${conversationId}`);
    const backend = createBackend({
      messages: {
        [conversationId]: [
          textMessage("207", conversationId, "user", "请先了解我的偏好"),
          questionMessage,
          textMessage(
            "208",
            conversationId,
            "user",
            "用户已提交以下选择：\n- 你偏好的工作方式是什么？：团队协作",
          ),
          textMessage("209", conversationId, "assistant", "我会按团队协作的方式展开。"),
        ],
      },
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    expect(await screen.findByText(/已提交回答 · 共 1 题/)).toBeInTheDocument();
    expect(screen.getByText("你偏好的工作方式是什么？")).toBeInTheDocument();
    expect(screen.getByText("团队协作", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText(/已完成答题 · 共 1 题/)).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });
});
