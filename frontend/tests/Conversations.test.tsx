import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/app/App";
import type {
  ConversationMessage,
  ConversationSummary,
  QuestionContentPart,
  SubmittedQuestionAnswer,
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

function submittedAnswerMessage(
  id: string,
  conversationId: string,
  text: string,
  items: SubmittedQuestionAnswer[],
): ConversationMessage {
  const message = textMessage(id, conversationId, "user", text);
  message.content.parts.push({ type: "question_answers", items });
  return message;
}

function imageResultMessage(id: string, conversationId: string): ConversationMessage {
  return {
    id,
    conversation_id: conversationId,
    role: "assistant",
    content: {
      parts: [
        { type: "text", text: "图片已生成并保存到本次会话。" },
        {
          type: "image_result",
          task_result_id: "9007199254740994",
          generation_status: "succeeded",
          image_url: "/api/v1/task-results/9007199254740994/image",
        },
      ],
    },
    created_at: createdAt,
  };
}

function createSseResponse(
  events: Array<{ event_type: "start" | "message" | "heartbeat" | "end"; data: unknown }>,
  endGate?: Promise<void>,
  signal?: AbortSignal | null,
  deliveryGate?: Promise<void>,
  onEnd?: () => void,
): Response {
  const eventChunks = events.map((event, index) => {
    const envelope = {
      event_id: `evt_${index.toString(16).padStart(32, "0")}`,
      event_type: event.event_type,
      timestamp: Date.now(),
      data: event.data,
    };
    const bytes = new TextEncoder().encode(
      `id: ${envelope.event_id}\nevent: ${event.event_type}\ndata: ${JSON.stringify(envelope)}\n\n`,
    );
    const chunks: Uint8Array[] = [];
    for (let offset = 0; offset < bytes.length; offset += 11) {
      chunks.push(bytes.slice(offset, offset + 11));
    }
    return chunks;
  });

  let eventIndex = 0;
  let chunkIndex = 0;
  let endGateReleased = false;
  let endActionCompleted = false;
  async function waitForGate(gate: Promise<void>): Promise<void> {
    if (!signal) {
      await gate;
      return;
    }
    await new Promise<void>((resolve, reject) => {
      const cleanup = () => signal.removeEventListener("abort", abort);
      const abort = () => {
        cleanup();
        reject(new DOMException("Request aborted", "AbortError"));
      };
      signal.addEventListener("abort", abort, { once: true });
      void gate.then(
        () => {
          cleanup();
          resolve();
        },
        (error: unknown) => {
          cleanup();
          reject(error);
        },
      );
    });
  }
  const readChunk = async (): Promise<ReadableStreamReadResult<Uint8Array>> => {
    if (signal?.aborted) throw new DOMException("Request aborted", "AbortError");
    if (eventIndex >= eventChunks.length) return { done: true, value: undefined };
    if (events[eventIndex]?.event_type === "end" && endGate && !endGateReleased) {
      await waitForGate(endGate);
      endGateReleased = true;
    }
    if (signal?.aborted) throw new DOMException("Request aborted", "AbortError");
    if (events[eventIndex]?.event_type === "end" && !endActionCompleted) {
      onEnd?.();
      endActionCompleted = true;
      if (deliveryGate) await waitForGate(deliveryGate);
    }

    const chunks = eventChunks[eventIndex] ?? [];
    const value = chunks[chunkIndex];
    if (!value) {
      eventIndex += 1;
      chunkIndex = 0;
      return readChunk();
    }
    chunkIndex += 1;
    return { done: false, value };
  };
  const body = {
    getReader: () => ({
      read: readChunk,
      releaseLock: () => undefined,
    }),
  };

  return {
    ok: true,
    status: 200,
    headers: { get: () => "text/event-stream; charset=utf-8" },
    body,
  } as unknown as Response;
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
  streamEndGate?: Promise<void>;
  streamDeliveryGate?: Promise<void>;
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

      if (url.pathname === "/api/resume" && method === "GET") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            exists: false,
            content: {
              basic_info: {
                name: "",
                phone: "",
                email: "",
                intended_position: "",
                work_experience_years: null,
                photo_id: null,
              },
              educations: [],
              skills: {
                type: "doc",
                content: [{ type: "paragraph", content: [] }],
              },
              works: [],
              projects: [],
            },
            style_config: {
              font_size_pt: 10,
              line_height: 1.4,
              section_spacing_pt: 12,
              page_margin_mm: { top: 14, right: 14, bottom: 14, left: 14 },
              heading_color: "#2563eb",
            },
          }),
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
                name: "对话助手",
                description: "支持日常问答和多轮对话",
                type: "agent",
                status: "published",
                created_at: createdAt,
                added_at: createdAt,
                is_added: true,
              },
              {
                id: "373284764594991101",
                code: "image_agent",
                name: "图片助手",
                description: "根据文字生成商品图片",
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
          skill_code: typeof body?.skill_code === "string" ? body.skill_code : "general_chat",
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
          json: async () => ({
            items: conversations.slice(offset, offset + limit),
            limit,
            offset,
            total_count: conversations.length,
          }),
        } as Response;
      }

      const isMessageStream = url.pathname.endsWith("/messages/stream");
      const messageRoute = url.pathname.match(
        /^\/api\/conversations\/([^/]+)\/messages(?:\/stream)?$/,
      );
      if (messageRoute && method === "GET" && !isMessageStream) {
        const conversationId = messageRoute[1];
        const items = messages.get(conversationId) ?? [];
        const skill_code =
          conversations.find((item) => item.id === conversationId)?.skill_code ?? "general_chat";
        const limit = Number(url.searchParams.get("limit") ?? 50);
        const offset = Number(url.searchParams.get("offset") ?? 0);
        return {
          ok: true,
          status: 200,
          json: async () => ({
            items: items.slice(offset, offset + limit),
            skill_code,
            limit,
            offset,
          }),
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
        messages.set(conversationId, items);
        const persistAssistantMessage = () => {
          items.push(assistantMessage);
          messages.set(conversationId, items);
          const conversation = conversations.find((item) => item.id === conversationId);
          if (conversation) {
            conversation.updated_at = createdAt;
            if (!conversation.title && items.filter((item) => item.role === "user").length === 1) {
              conversation.title = "首条消息自动标题";
            }
          }
        };
        if (isMessageStream) {
          const assistantPart = assistantMessage.content.parts[0];
          const isQuestion = assistantPart?.type === "question";
          if (isQuestion) persistAssistantMessage();
          const messageEvents = isQuestion
            ? [{ type: "question", message: assistantMessage }]
            : ((assistantPart?.type === "text" ? assistantPart.text : "")
                .match(/.{1,8}/gu)
                ?.map((content) => ({ type: "text_delta", content })) ?? []);
          return createSseResponse(
            [
              { event_type: "start", data: {} },
              ...messageEvents.map((data) => ({ event_type: "message" as const, data })),
              { event_type: "end", data: { status: "completed" } },
            ],
            options?.streamEndGate,
            init?.signal,
            options?.streamDeliveryGate,
            isQuestion ? undefined : persistAssistantMessage,
          );
        }

        persistAssistantMessage();

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

      const isAnswersStream = url.pathname.endsWith("/answers/stream");
      const answersRoute = url.pathname.match(
        /^\/api\/conversations\/([^/]+)\/answers(?:\/stream)?$/,
      );
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
        const userAnswerMessage = latestQuestion
          ? submittedAnswerMessage(
              String(nextMessageId++),
              conversationId,
              answerText,
              latestQuestion.questions.map((question) => ({
                question_id: question.id,
                question: question.title,
                answer: String(answers[question.id] ?? ""),
              })),
            )
          : textMessage(String(nextMessageId++), conversationId, "user", answerText);
        items.push(userAnswerMessage);
        const assistantMessage = textMessage(
          String(nextMessageId++),
          conversationId,
          "assistant",
          "已按选择继续对话。",
        );
        messages.set(conversationId, items);
        const persistAssistantMessage = () => {
          items.push(assistantMessage);
          messages.set(conversationId, items);
        };
        if (isAnswersStream) {
          const answer = assistantMessage.content.parts[0];
          const messageEvents =
            answer?.type === "text"
              ? answer.text.match(/.{1,8}/gu)?.map((content) => ({ type: "text_delta", content }))
              : [];
          return createSseResponse(
            [
              { event_type: "start", data: {} },
              ...(messageEvents ?? []).map((data) => ({ event_type: "message" as const, data })),
              { event_type: "end", data: { status: "completed" } },
            ],
            options?.streamEndGate,
            init?.signal,
            options?.streamDeliveryGate,
            persistAssistantMessage,
          );
        }

        persistAssistantMessage();

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
  it("shows streamed answer text before the turn ends", async () => {
    window.history.replaceState({}, "", "/chat");
    let releaseEnd!: () => void;
    const endGate = new Promise<void>((resolve) => {
      releaseEnd = resolve;
    });
    const backend = createBackend({ streamEndGate: endGate });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole("textbox", { name: "发送消息" }), {
      target: { value: "实时流式" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText("已回答：实时流式")).toBeInTheDocument();
    expect(screen.getByText("助手正在生成…")).toBeInTheDocument();
    releaseEnd();
    await waitFor(() => {
      expect(screen.queryByText("助手正在生成…")).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows streamed resume assistant text before the turn ends", async () => {
    window.history.replaceState({}, "", "/resume");
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn() })),
    );
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        disconnect() {}
      },
    );
    let releaseEnd!: () => void;
    const endGate = new Promise<void>((resolve) => {
      releaseEnd = resolve;
    });
    const backend = createBackend({ streamEndGate: endGate });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole("textbox", { name: "发送消息" }), {
      target: { value: "简历助手实时流式" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText("已回答：简历助手实时流式")).toBeInTheDocument();
    expect(screen.getByText("助手正在生成…")).toBeInTheDocument();
    releaseEnd();
    await waitFor(() => {
      expect(screen.queryByText("助手正在生成…")).not.toBeInTheDocument();
    });
  });

  it("marks partial streamed text as incomplete after switching conversations", async () => {
    const activeConversationId = "9100000000000010";
    const otherConversationId = "9100000000000011";
    const endGate = new Promise<void>(() => undefined);
    window.history.replaceState({}, "", `/chat/${activeConversationId}`);
    const backend = createBackend({
      conversations: [
        {
          id: activeConversationId,
          skill_code: "general_chat",
          title: "当前会话",
          created_at: createdAt,
          updated_at: createdAt,
        },
        {
          id: otherConversationId,
          skill_code: "general_chat",
          title: "另一个会话",
          created_at: createdAt,
          updated_at: createdAt,
        },
      ],
      messages: {
        [activeConversationId]: [
          textMessage("210", activeConversationId, "user", "之前的问题"),
          textMessage("211", activeConversationId, "assistant", "之前的回答"),
        ],
        [otherConversationId]: [
          textMessage("212", otherConversationId, "user", "另一段会话的记录"),
        ],
      },
      streamEndGate: endGate,
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole("textbox", { name: "发送消息" }), {
      target: { value: "继续追问" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    expect(await screen.findByText("已回答：继续追问")).toBeInTheDocument();
    expect(screen.getByText("助手正在生成…")).toBeInTheDocument();

    window.history.pushState({}, "", `/chat/${otherConversationId}`);
    fireEvent.popState(window);
    expect(await screen.findByText("另一段会话的记录")).toBeInTheDocument();

    window.history.pushState({}, "", `/chat/${activeConversationId}`);
    fireEvent.popState(window);
    expect(await screen.findByRole("article", { name: "未完成的助手回答" })).toBeInTheDocument();
    expect(screen.getByText("回答未完成，刷新后不会保留这部分内容。")).toBeInTheDocument();
    expect(screen.queryByText("助手正在生成…")).not.toBeInTheDocument();
  });

  it("uses the saved answer when disconnect happens before the end event", async () => {
    const activeConversationId = "9100000000000012";
    const otherConversationId = "9100000000000013";
    const deliveryGate = new Promise<void>(() => undefined);
    window.history.replaceState({}, "", `/chat/${activeConversationId}`);
    const backend = createBackend({
      conversations: [
        {
          id: activeConversationId,
          skill_code: "general_chat",
          title: "当前会话",
          created_at: createdAt,
          updated_at: createdAt,
        },
        {
          id: otherConversationId,
          skill_code: "general_chat",
          title: "另一个会话",
          created_at: createdAt,
          updated_at: createdAt,
        },
      ],
      messages: {
        [activeConversationId]: [
          textMessage("213", activeConversationId, "user", "之前的问题"),
          textMessage("214", activeConversationId, "assistant", "之前的回答"),
        ],
        [otherConversationId]: [
          textMessage("215", otherConversationId, "user", "另一段会话的记录"),
        ],
      },
      streamDeliveryGate: deliveryGate,
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.change(await screen.findByRole("textbox", { name: "发送消息" }), {
      target: { value: "结束事件前断开" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
    expect(await screen.findByText("已回答：结束事件前断开")).toBeInTheDocument();
    expect(screen.getByText("助手正在生成…")).toBeInTheDocument();

    window.history.pushState({}, "", `/chat/${otherConversationId}`);
    fireEvent.popState(window);
    expect(await screen.findByText("另一段会话的记录")).toBeInTheDocument();

    window.history.pushState({}, "", `/chat/${activeConversationId}`);
    fireEvent.popState(window);
    expect(await screen.findByText("已回答：结束事件前断开")).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: "未完成的助手回答" })).not.toBeInTheDocument();
    expect(screen.queryByText("助手正在生成…")).not.toBeInTheDocument();
  });

  it("creates a conversation on first send and continues multi-turn messages with the string ID", async () => {
    window.history.replaceState({}, "", "/agents");
    const backend = createBackend();
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.click((await screen.findAllByRole("button", { name: "使用" }))[0]!);
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
          url.pathname === `/api/conversations/${createdConversationId}/messages/stream` &&
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

  it("starts a conversation bound to the image assistant from My Skills", async () => {
    window.history.replaceState({}, "", "/agents");
    const backend = createBackend();
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    fireEvent.click((await screen.findAllByRole("button", { name: "使用" }))[1]!);

    await waitFor(() => expect(window.location.pathname).toBe(`/chat/${createdConversationId}`));
    expect(
      backend.calls.some(
        ({ url, method, body }) =>
          url.pathname === "/api/conversations" &&
          method === "POST" &&
          body?.skill_code === "image_agent",
      ),
    ).toBe(true);
    await waitFor(() => {
      expect(document.querySelector(".conversation-panel__header h1")?.textContent).toBe(
        "图片助手",
      );
    });
  });

  it("restores image assistant identity and shows a private image result", async () => {
    const conversationId = "9100000000000020";
    window.history.replaceState({}, "", `/chat/${conversationId}`);
    const backend = createBackend({
      conversations: [
        {
          id: conversationId,
          skill_code: "image_agent",
          title: "白色陶瓷杯主图",
          created_at: createdAt,
          updated_at: createdAt,
        },
      ],
      messages: {
        [conversationId]: [
          textMessage("220", conversationId, "user", "生成一张白色陶瓷杯主图"),
          imageResultMessage("221", conversationId),
        ],
      },
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    expect(await screen.findByText("图片已生成并保存到本次会话。")).toBeInTheDocument();
    expect(document.querySelector(".conversation-panel__header h1")?.textContent).toBe("图片助手");
    const image = screen.getByRole("img", { name: "图片助手生成的商品图片" });
    expect(image).toHaveAttribute("src", "/api/v1/task-results/9007199254740994/image");
    const bubble = image.closest(".conversation-message__bubble");
    expect(bubble).toContainElement(screen.getByText("图片已生成并保存到本次会话。"));
    expect(screen.getByRole("link", { name: "查看生成图片原图" })).toHaveAttribute(
      "href",
      "/api/v1/task-results/9007199254740994/image",
    );
    fireEvent.error(image);
    expect(screen.getByText("生成图片暂时无法显示。")).toHaveAttribute("role", "status");
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
    const answerCard = screen.getByRole("region", { name: "我的回答，共 1 题" });
    expect(within(answerCard).getByText("你希望回答采用哪种风格？")).toBeInTheDocument();
    expect(within(answerCard).getByText("简洁")).toBeInTheDocument();

    const completedCard = screen.getByRole("region", { name: "本轮答题已完成，共 1 题" });
    const completedToggle = within(completedCard).getByRole("button", {
      name: /本轮答题已完成.*共 1 题/,
    });
    expect(completedToggle).toHaveAttribute("aria-expanded", "false");
    const questionDetails = document.getElementById(completedToggle.getAttribute("aria-controls")!);
    expect(questionDetails).toHaveAttribute("aria-hidden", "true");
    fireEvent.click(completedToggle);
    expect(completedToggle).toHaveAttribute("aria-expanded", "true");
    expect(within(questionDetails!).getByText("你希望回答采用哪种风格？")).toBeInTheDocument();
    expect(within(questionDetails!).queryByRole("radio")).not.toBeInTheDocument();
    fireEvent.click(completedToggle);
    expect(completedToggle).toHaveAttribute("aria-expanded", "false");
    expect(
      document.querySelector(".conversation-message--user .conversation-message__label"),
    ).toBeNull();
    expect(
      backend.calls.some(
        ({ url, method, body }) =>
          url.pathname === `/api/conversations/${createdConversationId}/answers/stream` &&
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
      if (failNextAnswer && url.pathname.endsWith("/answers/stream") && init?.method === "POST") {
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

    expect(await screen.findByRole("alert")).toHaveTextContent("对话服务暂不可用，请稍后重试。");
    expect(screen.getByRole("radio", { name: /简洁/ })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByRole("region", { name: "我的回答，共 1 题" })).toBeInTheDocument();
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
        ({ method, url }) => method === "POST" && url.pathname.endsWith("/answers/stream"),
      ),
    ).toBe(false);

    fireEvent.click(screen.getByRole("radio", { name: /技术成长/ }));
    fireEvent.click(screen.getByRole("button", { name: "提交答案" }));

    expect(await screen.findByText("已按选择继续对话。")).toBeInTheDocument();
    const answerCard = screen.getByRole("region", { name: "我的回答，共 3 题" });
    expect(within(answerCard).getByText("你目前遇到的主要问题是什么？")).toBeInTheDocument();
    expect(within(answerCard).getByText("选择一")).toBeInTheDocument();
    expect(within(answerCard).getByText("1–3 年")).toBeInTheDocument();
    expect(within(answerCard).getByText("技术成长")).toBeInTheDocument();
    const answerToggle = within(answerCard).getByRole("button", { name: /我的回答已提交/ });
    expect(answerToggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(answerToggle);
    const answerItems = within(answerCard).getAllByRole("listitem");
    expect(answerItems).toHaveLength(3);
    expect(answerItems[0]).toHaveTextContent("01你目前遇到的主要问题是什么？我的选择：选择一");
    expect(answerItems[1]).toHaveTextContent("02你目前的工作年限是多少？我的选择：1–3 年");
    expect(answerItems[2]).toHaveTextContent("03你最看重工作的哪一方面？我的选择：技术成长");
    expect(screen.queryByRole("button", { name: "提交答案" })).not.toBeInTheDocument();

    const answerCall = backend.calls.find(
      ({ method, url }) => method === "POST" && url.pathname.endsWith("/answers/stream"),
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
        ({ method, url }) => method === "POST" && url.pathname.endsWith("/messages/stream"),
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
      if (url.pathname.endsWith("/messages/stream") && init?.method === "POST") {
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
    expect(await screen.findByText("助手正在生成…")).toBeInTheDocument();
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
      skill_code: "general_chat",
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

  it("fits a page to the available session area and switches without navigation", async () => {
    const conversations: ConversationSummary[] = Array.from({ length: 32 }, (_, index) => ({
      id: `91000000000000${index + 10}`,
      skill_code: "general_chat",
      title: `分页会话 ${index + 1}`,
      created_at: createdAt,
      updated_at: createdAt,
    }));
    window.history.replaceState({}, "", "/sessions");
    const backend = createBackend({ conversations });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    expect(await screen.findByText("分页会话 1", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("共 32 条会话")).toBeInTheDocument();
    const firstPageRequest = backend.calls.find(
      ({ url, method }) =>
        method === "GET" &&
        url.pathname === "/api/conversations" &&
        url.searchParams.get("offset") === "0",
    );
    expect(firstPageRequest).toBeDefined();
    const pageSize = Number(firstPageRequest?.url.searchParams.get("limit"));
    expect(pageSize).toBeGreaterThan(0);
    expect(screen.getByText(`分页会话 ${pageSize}`, { exact: true })).toBeInTheDocument();
    expect(screen.queryByText(`分页会话 ${pageSize + 1}`, { exact: true })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "下一页" }));

    expect(
      await screen.findByText(`分页会话 ${pageSize + 1}`, { exact: true }),
    ).toBeInTheDocument();
    expect(screen.queryByText("分页会话 1", { exact: true })).not.toBeInTheDocument();
    expect(window.location.pathname).toBe("/sessions");
    expect(
      backend.calls.some(
        ({ url, method }) =>
          method === "GET" &&
          url.pathname === "/api/conversations" &&
          url.searchParams.get("limit") === String(pageSize) &&
          url.searchParams.get("offset") === String(pageSize),
      ),
    ).toBe(true);
  });

  it("keeps legacy answer text and restores its completed question card", async () => {
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

    expect(await screen.findByText(/用户已提交以下选择/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: /我的回答/ })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "本轮答题已完成，共 1 题" })).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });

  it("restores structured answers and expandable questions from historical messages", async () => {
    const conversationId = "9100000000000005";
    const question = singleChoiceQuestion("work_style", "你偏好的工作方式是什么？", [
      "独立完成",
      "团队协作",
      "灵活切换",
    ]);
    const questionMessage: ConversationMessage = {
      id: "216",
      conversation_id: conversationId,
      role: "assistant",
      content: { parts: [{ type: "question", questions: [question] }] },
      created_at: createdAt,
    };
    window.history.replaceState({}, "", `/chat/${conversationId}`);
    const backend = createBackend({
      messages: {
        [conversationId]: [
          textMessage("217", conversationId, "user", "请先了解我的偏好"),
          questionMessage,
          submittedAnswerMessage(
            "218",
            conversationId,
            "用户已提交以下选择：\n- 你偏好的工作方式是什么？：团队协作",
            [
              {
                question_id: "work_style",
                question: "你偏好的工作方式是什么？",
                answer: "团队协作",
              },
            ],
          ),
          textMessage("219", conversationId, "assistant", "我会按团队协作的方式展开。"),
        ],
      },
    });
    vi.stubGlobal("fetch", backend.fetchMock);
    render(<App />);

    const answerCard = await screen.findByRole("region", { name: "我的回答，共 1 题" });
    expect(within(answerCard).getByText("团队协作")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "本轮答题已完成，共 1 题" })).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });
});
