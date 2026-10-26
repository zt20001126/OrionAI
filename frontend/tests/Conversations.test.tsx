import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/app/App";
import type {
  ConversationMessage,
  ConversationSummary,
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
        const assistantMessage =
          userText === "请先问我一个选择题"
            ? {
                id: String(nextMessageId++),
                conversation_id: conversationId,
                role: "assistant" as const,
                content: {
                  parts: [
                    {
                      type: "question" as const,
                      questions: [
                        {
                          id: "response_style",
                          title: "你希望回答采用哪种风格？",
                          type: "SingleChoice" as const,
                          allow_custom_input: false as const,
                          options: [
                            { label: "简洁", description: "优先使用较短内容。" },
                            { label: "详细", description: "提供背景和步骤。" },
                            { label: "正式", description: "采用正式书面表达。" },
                            { label: "轻松", description: "采用轻松自然的语气。" },
                          ],
                        },
                      ],
                    },
                  ],
                },
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
        if (conversation) conversation.updated_at = createdAt;
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
        const answers = body?.answers ?? {};
        items.push(
          textMessage(
            String(nextMessageId++),
            conversationId,
            "user",
            `已提交选择：${JSON.stringify(answers)}`,
          ),
        );
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

    fireEvent.click(await screen.findByRole("button", { name: /通用对话助手/ }));
    expect(await screen.findByText("有什么问题，尽管问我。")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "发送消息" }), {
      target: { value: "你好" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    expect(await screen.findByText("已回答：你好")).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: "提交选择" }));

    expect(await screen.findByText("已按选择继续对话。")).toBeInTheDocument();
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
});
