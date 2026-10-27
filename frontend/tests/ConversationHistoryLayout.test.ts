/// <reference types="node" />

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const conversationStyles = readFileSync(
  resolve(process.cwd(), "src/features/conversations/conversations.css"),
  "utf8",
);

describe("conversation history layout", () => {
  it("keeps sidebar history rows stacked at the top of the scroll area", () => {
    const historyListRule = conversationStyles.match(/\.conversation-history__list\s*\{([^}]*)\}/);

    expect(historyListRule?.[1] ?? "").toMatch(/align-content:\s*start/);
  });
});
