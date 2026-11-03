import { afterEach, describe, expect, it, vi } from "vitest";

import { streamConversationMessage } from "./conversationApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamConversationMessage", () => {
  it("sends an optional idempotency key without changing the stream protocol", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "幂等键已用于另一条消息，请重新发送。" }), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      streamConversationMessage(
        "12",
        "你好",
        vi.fn(),
        new AbortController().signal,
        "request-uuid",
      ),
    ).rejects.toThrow("幂等键已用于另一条消息，请重新发送。");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/conversations/12/messages/stream",
      expect.objectContaining({
        headers: { "Content-Type": "application/json", "Idempotency-Key": "request-uuid" },
      }),
    );
  });
});
