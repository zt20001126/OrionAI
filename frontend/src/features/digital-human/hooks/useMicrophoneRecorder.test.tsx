import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useMicrophoneRecorder } from "./useMicrophoneRecorder";

class MockMediaRecorder {
  static isTypeSupported() {
    return true;
  }

  readonly mimeType = "audio/webm;codecs=opus";
  state: "inactive" | "recording" | "paused" = "inactive";
  ondataavailable: ((event: BlobEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onstop: ((event: Event) => void) | null = null;
  stopCalls = 0;

  start() {
    this.state = "recording";
  }

  stop() {
    this.stopCalls += 1;
    this.state = "inactive";
    this.onstop?.(new Event("stop"));
  }
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useMicrophoneRecorder", () => {
  it("marks microphone permission startup as busy", async () => {
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    const stream = { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream;
    let resolveStream: (value: MediaStream) => void = () => undefined;
    const permissionRequest = new Promise<MediaStream>((resolve) => {
      resolveStream = resolve;
    });
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn(() => permissionRequest) },
    });
    const { result } = renderHook(() => useMicrophoneRecorder({ onTranscribed: vi.fn() }));
    let starting = Promise.resolve();

    act(() => {
      starting = result.current.startRecording();
    });
    expect(result.current.status).toBe("starting");

    await act(async () => {
      resolveStream(stream);
      await starting;
    });
    expect(result.current.status).toBe("listening");
  });

  it("automatically stops a recording after 30 seconds", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    const stopTrack = vi.fn();
    const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    const { result } = renderHook(() => useMicrophoneRecorder({ onTranscribed: vi.fn() }));

    await act(async () => {
      await result.current.startRecording();
    });
    expect(result.current.status).toBe("listening");

    act(() => {
      vi.advanceTimersByTime(29_999);
    });
    expect(result.current.status).toBe("listening");

    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(result.current.status).toBe("idle");
    expect(stopTrack).toHaveBeenCalled();
  });
});
