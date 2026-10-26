import { describe, expect, it } from "vitest";

import viteConfig from "../vite.config";

describe("Vite API proxy", () => {
  it("preserves the browser host so backend Origin validation succeeds", () => {
    const config = viteConfig({ mode: "test", command: "serve" });
    const proxy = config.server?.proxy as Record<string, { changeOrigin?: boolean }>;

    expect(proxy["/api"].changeOrigin).toBe(false);
  });
});
