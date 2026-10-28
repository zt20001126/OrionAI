import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../src/app/App";

const marketSkills = [
  {
    id: "373284764594991100",
    code: "general_chat",
    name: "对话助手",
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
    if (path === "/api/v1/users/me") {
      return {
        ok: true,
        json: async () => ({
          nickname: "示例用户",
          account: "person@example.com",
          avatar_url: "/avatar/default_avatar.png",
          created_at: "2025-03-10T14:26:08+08:00",
          last_login_at: null,
        }),
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
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("OrionAI platform", () => {
  it("opens the reminder creation route and returns to the list with browser back", async () => {
    window.history.replaceState({}, "", "/reminders");
    const sessionFetch = mockSession();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).startsWith("/api/v1/reminders")) {
        return {
          ok: true,
          json: async () => ({ items: [], total: 0, limit: 100, offset: 0 }),
        } as Response;
      }
      return sessionFetch(input, init);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "我的提醒" })).toBeInTheDocument();
    const entries = new Map<number, { path: string; state: unknown }>();
    const rememberCurrentEntry = () => {
      const state = window.history.state as { __orionHistoryIndex?: number };
      if (typeof state.__orionHistoryIndex === "number") {
        entries.set(state.__orionHistoryIndex, {
          path: window.location.pathname,
          state: window.history.state,
        });
      }
    };
    rememberCurrentEntry();

    fireEvent.click(screen.getByRole("button", { name: "新建提醒" }));
    expect(await screen.findByRole("heading", { name: "新建提醒" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/reminders/new");
    expect(screen.queryByRole("heading", { name: "我的提醒" })).not.toBeInTheDocument();
    rememberCurrentEntry();

    vi.spyOn(window.history, "go").mockImplementation((delta = 0) => {
      const current = window.history.state as { __orionHistoryIndex?: number };
      if (typeof current.__orionHistoryIndex !== "number") return;
      const target = entries.get(current.__orionHistoryIndex + delta);
      if (!target) return;
      window.history.replaceState(target.state, "", target.path);
      window.dispatchEvent(new PopStateEvent("popstate", { state: target.state }));
    });

    window.history.go(-1);
    expect(await screen.findByRole("heading", { name: "我的提醒" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/reminders");
    expect(screen.queryByRole("heading", { name: "新建提醒" })).not.toBeInTheDocument();
  });

  it("shows the skill market after restoring an authenticated session", async () => {
    vi.stubGlobal("fetch", mockSession());

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" }),
    ).toBeInTheDocument();
    await waitFor(() => expect(window.location.pathname).toBe("/market"));
    expect(screen.getByRole("link", { name: /技能市场/ })).toHaveAttribute("aria-current", "page");
    expect(await screen.findByRole("heading", { name: "简历助手" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "文献助手" })).toBeInTheDocument();
    expect(screen.getAllByText("已停用")).toHaveLength(2);
    expect(document.querySelectorAll(".skill-card__status--disabled")).toHaveLength(2);
    expect(screen.getByRole("heading", { name: "对话助手" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "文档处理工具" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "会话记录" }));
    expect(await screen.findByRole("heading", { name: "会话记录" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "会话记录" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("link", { name: "技能市场" }));
    expect(
      await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" }),
    ).toBeInTheDocument();
  });

  it("uses the custom leave dialog and preserves unsaved profile changes", async () => {
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" });
    fireEvent.click(screen.getByRole("button", { name: "更多用户选项" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "个人设置" }));

    const nicknameInput = await screen.findByRole("textbox", { name: "用户昵称" });
    fireEvent.change(nicknameInput, { target: { value: "待保存昵称" } });
    fireEvent.click(screen.getByRole("button", { name: "安全设置" }));

    expect(await screen.findByRole("dialog", { name: "离开当前页面？" })).toHaveTextContent(
      "当前修改尚未保存，离开后更改将丢失。",
    );
    fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(window.location.pathname).toBe("/settings");
    expect(nicknameInput).toHaveValue("待保存昵称");

    fireEvent.click(screen.getByRole("button", { name: "安全设置" }));
    fireEvent.click(await screen.findByRole("button", { name: "放弃修改并离开" }));
    await waitFor(() => expect(window.location.pathname).toBe("/settings/security"));
    const persistedNickname = document.getElementById(
      "profile-nickname",
    ) as HTMLInputElement | null;
    expect(persistedNickname?.value).toBe("待保存昵称");
  });

  it("keeps browser forward navigation on the requested route after confirmation", async () => {
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" });
    const entries = new Map<number, { path: string; state: unknown }>();
    const rememberCurrentEntry = () => {
      const state = window.history.state as { __orionHistoryIndex?: number };
      if (typeof state.__orionHistoryIndex === "number") {
        entries.set(state.__orionHistoryIndex, {
          path: window.location.pathname,
          state: window.history.state,
        });
      }
    };
    rememberCurrentEntry();

    fireEvent.click(screen.getByRole("button", { name: "更多用户选项" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "个人设置" }));
    await screen.findByRole("textbox", { name: "用户昵称" });
    rememberCurrentEntry();

    fireEvent.click(screen.getByRole("link", { name: "技能市场" }));
    await screen.findByRole("heading", { name: "探索 AI 技能，构建专属智能体" });
    rememberCurrentEntry();

    vi.spyOn(window.history, "go").mockImplementation((delta = 0) => {
      const current = window.history.state as { __orionHistoryIndex?: number };
      if (typeof current.__orionHistoryIndex !== "number") return;
      const target = entries.get(current.__orionHistoryIndex + delta);
      if (!target) return;
      window.history.replaceState(target.state, "", target.path);
      window.dispatchEvent(new PopStateEvent("popstate", { state: target.state }));
    });

    window.history.go(-1);
    const nicknameInput = await screen.findByRole("textbox", { name: "用户昵称" });
    fireEvent.change(nicknameInput, { target: { value: "待保存昵称" } });

    window.history.go(1);
    expect(await screen.findByRole("dialog", { name: "离开当前页面？" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    await waitFor(() => expect(window.location.pathname).toBe("/settings"));
    expect(nicknameInput).toHaveValue("待保存昵称");

    window.history.go(1);
    expect(await screen.findByRole("dialog", { name: "离开当前页面？" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "放弃修改并离开" }));
    await waitFor(() => expect(window.location.pathname).toBe("/market"));
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

    fireEvent.click(await screen.findByRole("button", { name: "添加技能" }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "运行入口未接入" })).toBeInTheDocument();
    });
    expect(await screen.findByText("已添加「文档处理工具」到我的技能。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "我的技能" }));
    expect(await screen.findByRole("heading", { name: "我的技能" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "文档处理工具" })).toBeInTheDocument();
  });

  it("removes a skill from my skills", async () => {
    window.history.replaceState({}, "", "/agents");
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    expect(await screen.findByRole("heading", { name: "对话助手" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "移除" }));

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "对话助手" })).not.toBeInTheDocument();
    });
    expect(await screen.findByText("已从我的技能移除「对话助手」。")).toBeInTheDocument();
    expect(screen.getByText("0 项技能")).toBeInTheDocument();
  });

  it("shows only added skills on my skills page and preserves other placeholders", async () => {
    window.history.replaceState({}, "", "/agents");
    vi.stubGlobal("fetch", mockSession());
    render(<App />);

    expect(await screen.findByRole("heading", { name: "我的技能" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "对话助手" })).toBeInTheDocument();
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
    await waitFor(() => expect(window.location.pathname).toBe("/login"));
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
