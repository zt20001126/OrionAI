import { afterEach, describe, expect, it, vi } from "vitest";

import { createRequestKey } from "./requestKey";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createRequestKey", () => {
  it("uses crypto.randomUUID when available", () => {
    vi.stubGlobal("crypto", {
      randomUUID: vi.fn(() => "123e4567-e89b-42d3-a456-426614174000"),
    });

    expect(createRequestKey()).toBe("123e4567-e89b-42d3-a456-426614174000");
  });

  it("generates a v4 UUID from secure random values when randomUUID is unavailable", () => {
    vi.stubGlobal("crypto", {
      getRandomValues: vi.fn((bytes: Uint8Array) => {
        bytes.fill(0);
        return bytes;
      }),
    });

    expect(createRequestKey()).toBe("00000000-0000-4000-8000-000000000000");
  });
});
