import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/app/App";

function mockSession(account: string | null = "person@example.com") {
  return vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const path = String(input);
    if (path.endsWith("/session")) {
      return {
        ok: true,
        json: async () => ({ authenticated: account !== null, account }),
      } as Response;
    }
    if (path.endsWith("/logout")) {
      return { ok: true, json: async () => ({ message: "已退出登录。" }) } as Response;
    }
    if (path.startsWith("/api/conversations")) {
      return {
        ok: true,
        json: async () => ({ items: [], limit: 50, offset: 0 }),
      } as Response;
    }
    return { ok: true, json: async () => ({ account: "person@example.com" }) } as Response;
  });
}

beforeEach(() => {
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, "", "/");
});

describe("OrionAI platform", () => {
  it("shows the skill market after restoring an authenticated session", async () => {
    vi.stubGlobal("fetch", mockSession());

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/market");
    expect(screen.getByRole("link", { name: /技能市场/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "RAG 知识问答" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "工具调用" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "文档分析" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "数据分析" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "会话记录" }));
    expect(await screen.findByRole("heading", { name: "会话记录" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "会话记录" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("link", { name: "技能市场" }));
    expect(
      await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" }),
    ).toBeInTheDocument();
  });

  it("filters demo skills by search and category", async () => {
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    const search = await screen.findByPlaceholderText("搜索技能（如：RAG、文档分析、代码助手等）");
    fireEvent.change(search, { target: { value: "文档" } });
    expect(screen.getByRole("heading", { name: "文档分析" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "RAG 知识问答" })).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "数据处理" }));
    expect(screen.getByRole("heading", { name: "文档分析" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "数据分析" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "RAG 知识问答" })).not.toBeInTheDocument();
  });

  it("opens and closes skill details", async () => {
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "查看 RAG 知识问答 详情" }));
    expect(screen.getByRole("dialog", { name: "RAG 知识问答" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "关闭技能详情" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the agent entry and session history while preserving other placeholders", async () => {
    window.history.replaceState({}, "", "/agents");
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    expect(await screen.findByRole("heading", { name: "我的智能体" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /通用对话助手/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /添加智能体，暂未开放/ })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /通用对话助手/ }));
    expect(await screen.findByText("有什么问题，尽管问我。")).toBeInTheDocument();
    expect(window.location.pathname).toBe("/chat");

    fireEvent.click(screen.getByRole("link", { name: "会话记录" }));
    expect(await screen.findByRole("heading", { name: "会话记录" })).toBeInTheDocument();
    expect(await screen.findByText("还没有历史会话。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "知识库" }));
    expect(await screen.findByRole("heading", { name: "知识库" })).toBeInTheDocument();
    expect(screen.getByText("该页面正在建设中，敬请期待。")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: "工具管理" }));
    expect(await screen.findByRole("heading", { name: "工具管理" })).toBeInTheDocument();
  });

  it("redirects protected routes to login when signed out", async () => {
    window.history.replaceState({}, "", "/agents");
    vi.stubGlobal("fetch", mockSession(null));
    render(<App />);
    expect(await screen.findByRole("heading", { name: "登录 OrionAI" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
  });

  it("returns to login after logout", async () => {
    const fetchMock = mockSession();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "更多用户选项" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "退出登录" }));

    expect(await screen.findByRole("heading", { name: "登录 OrionAI" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/logout"))).toBe(true);
  });
});
