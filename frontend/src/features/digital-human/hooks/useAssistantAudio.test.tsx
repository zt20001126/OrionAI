import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useAssistantAudio } from "./useAssistantAudio";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useAssistantAudio", () => {
  it("plays generated audio and returns to idle when playback ends", async () => {
    const createObjectUrl = vi.fn(() => "blob:digital-human-reply");
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectUrl,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectUrl,
    });
    vi.stubGlobal("AudioContext", undefined);

    const { result } = renderHook(() => useAssistantAudio());
    const audio = document.createElement("audio");
    audio.play = vi.fn().mockResolvedValue(undefined);
    audio.pause = vi.fn();
    audio.load = vi.fn();
    result.current.audioRef.current = audio;
    let playback = Promise.resolve();

    act(() => {
      playback = result.current.playAudio(new Blob(["mp3"]));
    });
    await waitFor(() => expect(result.current.isSpeaking).toBe(true));

    act(() => {
      audio.onended?.(new Event("ended"));
    });
    await act(async () => {
      await playback;
    });

    expect(audio.play).toHaveBeenCalledOnce();
    expect(result.current.isSpeaking).toBe(false);
    expect(result.current.mouthOpen).toBe(0);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:digital-human-reply");
  });
});
