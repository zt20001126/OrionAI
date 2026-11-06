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
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:digital-human-reply");
  });
});

it("queues segments in order and stops pending playback", async () => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn().mockReturnValueOnce("blob:1").mockReturnValueOnce("blob:2"),
  });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  const { result, unmount } = renderHook(() => useAssistantAudio());
  const audio = document.createElement("audio");
  audio.play = vi.fn().mockResolvedValue(undefined);
  audio.pause = vi.fn();
  audio.load = vi.fn();
  result.current.audioRef.current = audio;
  act(() => {
    result.current.enqueueAudio(new Blob(["1"]), vi.fn());
    result.current.enqueueAudio(new Blob(["2"]), vi.fn());
  });
  await waitFor(() => expect(audio.play).toHaveBeenCalledTimes(1));
  act(() => audio.onended?.(new Event("ended")));
  await waitFor(() => expect(audio.play).toHaveBeenCalledTimes(2));
  expect(audio.src).toBe("blob:2");
  act(() => result.current.stopAudio());
  expect(audio.pause).toHaveBeenCalled();
  expect(result.current.isSpeaking).toBe(false);
  unmount();
});

it("releases queued audio on unmount and reports playback failure", async () => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:failure"),
  });
  const revoke = vi.fn();
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
  const { result, unmount } = renderHook(() => useAssistantAudio());
  const audio = document.createElement("audio");
  audio.play = vi.fn().mockRejectedValue(new Error("blocked"));
  audio.pause = vi.fn();
  audio.load = vi.fn();
  result.current.audioRef.current = audio;
  const onError = vi.fn();
  act(() => {
    void result.current.enqueueAudio(new Blob(["audio"]), onError);
  });
  await waitFor(() => expect(onError).toHaveBeenCalledOnce());
  expect(result.current.isSpeaking).toBe(false);
  expect(revoke).toHaveBeenCalledWith("blob:failure");
  unmount();
  expect(audio.pause).toHaveBeenCalled();
});

it("applies backpressure when eight segments are queued", async () => {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    value: vi.fn(() => "blob:queue"),
  });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  const { result } = renderHook(() => useAssistantAudio());
  const audio = document.createElement("audio");
  audio.play = vi.fn().mockResolvedValue(undefined);
  audio.pause = vi.fn();
  audio.load = vi.fn();
  result.current.audioRef.current = audio;
  let drained = false;
  act(() => {
    for (let index = 0; index < 8; index += 1) {
      const wait = result.current.enqueueAudio(new Blob(["audio"]), vi.fn());
      if (index === 7)
        void wait.then(() => {
          drained = true;
        });
    }
  });
  await waitFor(() => expect(audio.play).toHaveBeenCalledOnce());
  expect(drained).toBe(false);
  act(() => result.current.stopAudio());
  await waitFor(() => expect(drained).toBe(true));
  expect(audio.play).toHaveBeenCalledOnce();
});
