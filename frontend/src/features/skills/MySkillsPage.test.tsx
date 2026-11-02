import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ToastProvider";
import { MySkillsPage } from "./MySkillsPage";

const skillList = {
  items: [
    {
      id: "42",
      code: "general_chat",
      name: "对话助手",
      description: "日常问答和多轮对话",
      type: "agent",
      status: "published",
      created_at: "2026-11-02T00:00:00Z",
      is_added: true,
      added_at: "2026-11-02T00:00:00Z",
    },
  ],
};

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

function renderPage(onNavigate = vi.fn()) {
  return {
    onNavigate,
    ...render(
      <ToastProvider>
        <MySkillsPage onNavigate={onNavigate} />
      </ToastProvider>,
    ),
  };
}

describe("MySkillsPage membership access", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("checks membership on every use click and launches a member skill", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/v1/users/me/skills") return jsonResponse(skillList);
      if (path === "/api/v1/users/me/membership/access") {
        return jsonResponse({ is_member: true });
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { onNavigate } = renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "使用" }));
    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "使用" }));

    await waitFor(() => expect(onNavigate).toHaveBeenCalledTimes(2));
    const accessChecks = fetchMock.mock.calls.filter(
      ([input]) => String(input) === "/api/v1/users/me/membership/access",
    );
    expect(accessChecks).toHaveLength(2);
  });

  it("lets a nonmember close the notice without launching the skill", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) =>
      String(input) === "/api/v1/users/me/skills"
        ? jsonResponse(skillList)
        : jsonResponse({ is_member: false }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const { onNavigate } = renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "使用" }));

    await screen.findByRole("dialog", { name: "开通会员后即可使用" });
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(onNavigate).not.toHaveBeenCalled();
  });

  it("navigates a nonmember to the membership page when they choose recharge", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input) === "/api/v1/users/me/skills"
          ? jsonResponse(skillList)
          : jsonResponse({ is_member: false }),
      ),
    );
    const { onNavigate } = renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "使用" }));
    await screen.findByRole("dialog", { name: "开通会员后即可使用" });
    fireEvent.click(screen.getByRole("button", { name: "去充值" }));

    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith("/membership"));
  });

  it("does not launch a skill when membership status cannot be checked", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input) === "/api/v1/users/me/skills"
          ? jsonResponse(skillList)
          : jsonResponse({ detail: "会员服务暂时不可用，请稍后重试。" }, 503),
      ),
    );
    const { onNavigate } = renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "使用" }));

    expect(await screen.findByText("会员服务暂时不可用，请稍后重试。")).toBeInTheDocument();
    expect(onNavigate).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
