import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/app/App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("OrionAI base page", () => {
  it("shows the platform name and reports a healthy API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok", service: "OrionAI" }),
      }),
    );

    render(<App />);

    expect(screen.getByRole("heading", { name: "OrionAI" })).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("API 服务正常");
  });
});
