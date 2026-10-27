import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/app/App";

const marketSkills = [
  {
    id: "373284764594991100",
    code: "general_chat",
    name: "通用对话助手",
    description: "支持日常问答和多轮对话",
    type: "agent",
    status: "published",
    created_at: "2026-10-27T00:00:00Z",
    is_added: false,
  },
  {
    id: "373284764594991104",
    code: "resume_assistant",
    name: "简历助手",
    description: "提供简历分析、内容优化、岗位匹配及面试准备等智能服务。",
    type: "agent",
    status: "disabled",
    created_at: "2026-10-27T00:00:00Z",
    is_added: false,
  },
  {
    id: "373284764594991105",
    code: "literature_assistant",
    name: "文献助手",
    description: "提供学术文献解析、内容总结、文献问答及研究信息提取等智能服务。",
    type: "agent",
    status: "disabled",
    created_at: "2026-10-27T00:00:00Z",
    is_added: false,
  },
  {
    id: "373284764594991106",
    code: "document_tool",
    name: "文档处理工具",
    description: "整理文档中的主要信息。",
    type: "tool",
    status: "published",
    created_at: "2026-10-27T00:00:00Z",
    is_added: false,
  },
];

function mockSession(
  account: string | null = "person@example.com",
  initiallyAddedSkills: string[] = ["general_chat"],
) {
  const addedSkillCodes = new Set(initiallyAddedSkills);
  return vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.startsWith("/api/v1/skills")) {
      expect(path).toContain("include_disabled=true");
      expect(init?.credentials).toBe("include");
      return {
        ok: true,
        json: async () => ({
          items: marketSkills.map((skill) => ({
            ...skill,
            is_added: addedSkillCodes.has(skill.code),
          })),
          total: marketSkills.length,
          page: 1,
          page_size: 100,
        }),
      } as Response;
    }
    if (path === "/api/v1/users/me/skills" && init?.method === "POST") {
      const request = JSON.parse(String(init.body)) as { skill_id: string };
      const skill = marketSkills.find((item) => item.id === request.skill_id);
      if (!skill || skill.status === "disabled") {
        return { ok: false, json: async () => ({ detail: "技能不存在。" }) } as Response;
      }
      addedSkillCodes.add(skill.code);
      return {
        ok: true,
        json: async () => ({ ...skill, is_added: true }),
      } as Response;
    }
    if (path === "/api/v1/users/me/skills") {
      return {
        ok: true,
        json: async () => ({
          items: marketSkills
            .filter((skill) => addedSkillCodes.has(skill.code) && skill.status === "published")
            .map((skill) => ({ ...skill, is_added: true, added_at: "2026-10-27T00:00:00Z" })),
        }),
      } as Response;
    }
    if (path.startsWith("/api/v1/users/me/skills/") && init?.method === "DELETE") {
      const skillId = path.split("/").at(-1);
      const skill = marketSkills.find((item) => item.id === skillId);
      if (skill) addedSkillCodes.delete(skill.code);
      return { ok: true, json: async () => null } as Response;
    }
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
    expect(await screen.findByRole("heading", { name: "简历助手" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "文献助手" })).toBeInTheDocument();
    expect(screen.getAllByText("智能体 · 已停用")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "通用对话助手" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "文档处理工具" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "会话记录" }));
    expect(await screen.findByRole("heading", { name: "会话记录" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "会话记录" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("link", { name: "技能市场" }));
    expect(
      await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" }),
    ).toBeInTheDocument();
  });

  it("filters database skills by search and category", async () => {
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    const search = await screen.findByPlaceholderText("搜索技能名称、说明或编码");
    fireEvent.change(search, { target: { value: "文献" } });
    expect(await screen.findByRole("heading", { name: "文献助手" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "简历助手" })).not.toBeInTheDocument();

    fireEvent.change(search, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "工具" }));
    expect(await screen.findByRole("heading", { name: "文档处理工具" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "文献助手" })).not.toBeInTheDocument();
  });

  it("opens and closes skill details", async () => {
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "查看 文献助手 详情" }));
    expect(screen.getByRole("dialog", { name: "文献助手" })).toBeInTheDocument();
    expect(screen.getByText("该技能已停用，暂不可添加。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "关闭技能详情" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("adds a published skill to my skills", async () => {
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "添加到我的技能" }));
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: "已在我的技能" })).toHaveLength(2);
    });
    fireEvent.click(screen.getByRole("link", { name: "我的技能" }));
    expect(await screen.findByRole("heading", { name: "我的技能" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "文档处理工具" })).toBeInTheDocument();
  });

  it("shows only added skills on my skills page and preserves other placeholders", async () => {
    window.history.replaceState({}, "", "/agents");
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    expect(await screen.findByRole("heading", { name: "我的技能" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "通用对话助手" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "简历助手" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "使用" }));
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
