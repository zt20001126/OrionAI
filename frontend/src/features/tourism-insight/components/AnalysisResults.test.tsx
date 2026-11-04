import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { listTourismResults } from "../api/tourismInsightApi";
import type { TourismResults } from "../api/tourismInsightApi";
import { AnalysisResults } from "./AnalysisResults";

vi.mock("../api/tourismInsightApi", () => ({
  listTourismResults: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const result: TourismResults = {
  items: [
    {
      comment: {
        id: "comment-1",
        source_type: "manual",
        nickname: null,
        ugc_type: null,
        platform: null,
        title: null,
        content: "大厅指引清晰，卫生间很干净，排队很久。",
        published_at: null,
        analyzed: true,
      },
      matches: [
        {
          status: "matched",
          evidence: "大厅指引清晰",
          reason: "评价明确",
          sentiment: "positive",
          rule: null,
        },
        {
          status: "review",
          evidence: "卫生间很干净",
          reason: "需要核验评分口径",
          sentiment: "objective",
          rule: null,
        },
        {
          status: "unmatched",
          evidence: "排队很久",
          reason: null,
          sentiment: "negative",
          rule: null,
        },
        {
          status: "unmatched",
          evidence: "旧分析结果",
          reason: null,
          sentiment: null,
          rule: null,
        },
      ],
    },
  ],
  limit: 20,
  offset: 0,
};

describe("AnalysisResults", () => {
  it("shows each sentiment label and leaves historical null values unlabeled", async () => {
    vi.mocked(listTourismResults).mockResolvedValue(result);

    const { container } = render(<AnalysisResults reloadVersion={0} showToast={vi.fn()} />);

    expect(await screen.findByText("正向")).toBeInTheDocument();
    expect(screen.getByText("负向")).toBeInTheDocument();
    expect(screen.getByText("客观")).toBeInTheDocument();
    expect(container.querySelectorAll(".tourism-sentiment")).toHaveLength(3);
    expect(listTourismResults).toHaveBeenCalledOnce();
  });
});
