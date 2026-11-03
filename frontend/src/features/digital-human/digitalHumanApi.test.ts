import { afterEach, describe, expect, it, vi } from "vitest";

import { recognizeSpeech, synthesizeSpeech } from "./digitalHumanApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("digitalHumanApi", () => {
  it("uploads a short recording as multipart audio and returns editable text", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ text: "识别文本" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    const response = await recognizeSpeech(new Blob(["recording"], { type: "audio/webm" }));
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const form = request.body as FormData;

    expect(response).toEqual({ text: "识别文本" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/digital-human/speech/recognitions",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(form.get("file")).toMatchObject({ name: "recording.webm", type: "audio/webm" });
  });

  it("requests speech audio and rejects a non-audio response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response("audio-bytes", { status: 200, headers: { "Content-Type": "audio/mpeg" } }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const audio = await synthesizeSpeech("你好");
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;

    expect(audio.type).toBe("audio/mpeg");
    expect(request.headers).toEqual({ "Content-Type": "application/json" });
    expect(request.body).toBe(JSON.stringify({ text: "你好" }));

    fetchMock.mockResolvedValueOnce(
      new Response("not audio", { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    await expect(synthesizeSpeech("你好")).rejects.toThrow("语音服务未返回有效音频。");
  });
});
