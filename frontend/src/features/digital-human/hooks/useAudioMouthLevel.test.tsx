import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RefObject } from "react";

import { useAudioMouthLevel } from "./useAudioMouthLevel";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useAudioMouthLevel", () => {
  it("maps the playing audio envelope to a mouth level between zero and one", async () => {
    let frameCallback: FrameRequestCallback | null = null;
    const source = { connect: vi.fn(), disconnect: vi.fn() };
    const analyser = {
      connect: vi.fn(),
      disconnect: vi.fn(),
      fftSize: 256,
      getByteTimeDomainData: vi.fn((data: Uint8Array) => data.fill(200)),
      smoothingTimeConstant: 0,
    };

    class MockAudioContext {
      destination = {};
      resume = vi.fn().mockResolvedValue(undefined);
      close = vi.fn().mockResolvedValue(undefined);
      createAnalyser = vi.fn(() => analyser);
      createMediaElementSource = vi.fn(() => source);
    }

    vi.stubGlobal("AudioContext", MockAudioContext);
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      frameCallback = callback;
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", vi.fn());

    const audioRef = {
      current: { ended: false, paused: false },
    } as RefObject<HTMLAudioElement | null>;
    const { result, unmount } = renderHook(() => useAudioMouthLevel(audioRef, true));

    await act(async () => {
      await Promise.resolve();
    });
    act(() => {
      frameCallback?.(40);
    });

    expect(result.current).toBeGreaterThan(0);
    expect(result.current).toBeLessThanOrEqual(1);
    expect(analyser.getByteTimeDomainData).toHaveBeenCalledOnce();

    unmount();
    expect(source.disconnect).toHaveBeenCalledOnce();
  });
});
