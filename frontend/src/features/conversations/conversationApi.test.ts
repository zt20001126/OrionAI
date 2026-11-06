import { afterEach, describe, expect, it, vi } from "vitest";

import { streamConversationMessage } from "./conversationApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("streamConversationMessage", () => {
  it("sends an optional idempotency key when creating a background run", async () => {
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
      "/api/conversations/12/runs/messages",
      expect.objectContaining({
        headers: { "Content-Type": "application/json", "Idempotency-Key": "request-uuid" },
      }),
    );
  });
});

it("delivers audio before the stream ends and preserves text events", async () => {
  let release: (() => void) | undefined;
  const wait = new Promise<void>((resolve) => {
    release = resolve;
  });
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      controller.enqueue(
        encoder.encode(
          'data: {"event_type":"message","data":{"type":"text_delta","content":"你好"}}\n\n',
        ),
      );
      controller.enqueue(
        encoder.encode(
          'data: {"event_type":"message","data":{"type":"audio_segment","turn_id":"turn-1","segment_id":1,"audio":"aWQz"}}\n\n',
        ),
      );
      await wait;
      controller.enqueue(
        encoder.encode('data: {"event_type":"end","data":{"status":"completed"}}\n\n'),
      );
      controller.close();
    },
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream)));
  const onText = vi.fn();
  const onAudio = vi.fn();
  const { streamDigitalHumanReply } = await import("./conversationApi");
  const request = streamDigitalHumanReply(
    "12",
    "messages",
    { message: "你好" },
    onText,
    onAudio,
    new AbortController().signal,
  );
  await vi.waitFor(() => expect(onAudio).toHaveBeenCalledOnce());
  expect(onText).toHaveBeenCalledWith("你好");
  expect(onAudio).toHaveBeenCalledWith(
    expect.objectContaining({ turn_id: "turn-1", segment_id: 1 }),
  );
  release?.();
  await request;
});
