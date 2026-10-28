import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../src/components/ToastProvider";
import { ReminderPage } from "../src/features/reminders/ReminderPage";
import type { Reminder } from "../src/features/reminders/reminderApi";
import { platformPaths, type PlatformRoute } from "../src/features/platform/platformData";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("提醒助手管理页", () => {
  it("默认显示我的提醒；新建页隐藏列表，取消后返回且不创建", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.startsWith("/api/v1/reminders?")) return response(page([]));
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderReminderApp();

    expect(await screen.findByRole("heading", { name: "提醒助手" })).toBeInTheDocument();
    expect(screen.getByText("按计划将提醒发送到当前账号邮箱。")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "我的提醒" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "新建提醒" }));

    expect(await screen.findByRole("heading", { name: "新建提醒" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "我的提醒" })).not.toBeInTheDocument();
    expect(screen.queryByText("还没有提醒")).not.toBeInTheDocument();
    expect(
      screen.queryByText("默认使用浏览器时区；请填写 IANA 时区，例如 Asia/Shanghai。"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("邮件将发送到当前登录账号邮箱。系统会按所选时区处理提醒时间。"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "时区" })).toHaveValue(
      Intl.DateTimeFormat().resolvedOptions().timeZone,
    );

    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(await screen.findByRole("heading", { name: "我的提醒" })).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([path]) => String(path) === "/api/v1/reminders"),
    ).toHaveLength(0);
  });

  it("成功创建后回到列表并刷新，创建结果立即显示", async () => {
    let createdReminder: Reminder | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith("/api/v1/reminders?") && init?.method !== "POST") {
        return response(page(createdReminder ? [createdReminder] : []));
      }
      if (path === "/api/v1/reminders" && init?.method === "POST") {
        const payload = JSON.parse(String(init.body)) as {
          title: string;
          content: string;
          repeat_type: "once";
          timezone: string;
          date: string;
          local_time: string;
        };
        createdReminder = makeReminder("373284764594991100", payload.title, {
          ...payload,
          next_run_at: `${payload.date}T${payload.local_time}:00Z`,
        });
        return response(createdReminder);
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderReminderApp();
    expect(await screen.findByText("还没有提醒")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "新建提醒" }));
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "提交周报" } });
    fireEvent.change(screen.getByLabelText("内容"), { target: { value: "整理并提交本周进展。" } });
    fireEvent.click(screen.getByRole("button", { name: "保存提醒" }));

    expect(await screen.findByRole("heading", { name: "提交周报" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "我的提醒" })).toBeInTheDocument();
    expect(await screen.findByText("提醒已创建。")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([path]) => String(path).startsWith("/api/v1/reminders?")).length,
    ).toBeGreaterThanOrEqual(2);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/reminders",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });

  it("保存失败时留在新建页并保留已填写内容", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith("/api/v1/reminders?")) return response(page([]));
      if (path === "/api/v1/reminders" && init?.method === "POST") {
        return response({ detail: "提醒服务暂时不可用，请稍后重试。" }, 503);
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderReminderApp();
    await screen.findByText("还没有提醒");
    fireEvent.click(screen.getByRole("button", { name: "新建提醒" }));
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "保留我的标题" } });
    fireEvent.change(screen.getByLabelText("内容"), { target: { value: "保留我的内容" } });
    fireEvent.click(screen.getByRole("button", { name: "保存提醒" }));

    expect(await screen.findByRole("heading", { name: "新建提醒" })).toBeInTheDocument();
    expect(screen.getByLabelText("标题")).toHaveValue("保留我的标题");
    expect(screen.getByLabelText("内容")).toHaveValue("保留我的内容");
    expect(await screen.findByText("提醒服务暂时不可用，请稍后重试。")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "我的提醒" })).not.toBeInTheDocument();
  });

  it("重复方式可键盘操作，并按规则显示相应字段", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response(page([]))),
    );
    renderReminderApp();
    await screen.findByText("还没有提醒");
    fireEvent.click(screen.getByRole("button", { name: "新建提醒" }));

    const trigger = screen.getByRole("button", { name: "重复方式" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const listbox = await screen.findByRole("listbox", { name: "重复方式" });
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "Enter" });

    expect(screen.getByRole("button", { name: "重复方式" })).toHaveTextContent("每天重复");
    expect(screen.getByText("开始日期")).toBeInTheDocument();
    expect(screen.getByText("结束日期（可选）")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重复方式" }));
    fireEvent.click(screen.getByRole("option", { name: "每月重复" }));
    expect(
      screen.getByText("每月按开始日期的日号重复；当月份没有该日时会跳过。"),
    ).toBeInTheDocument();
  });

  it("日历可切换月份、选择日期并通过 Escape 关闭", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response(page([]))),
    );
    renderReminderApp();
    await screen.findByText("还没有提醒");
    fireEvent.click(screen.getByRole("button", { name: "新建提醒" }));

    fireEvent.click(screen.getByRole("button", { name: "提醒日期" }));
    const calendar = await screen.findByRole("dialog", { name: "选择日期" });
    const monthLabel =
      calendar.querySelector(".reminder-calendar-header strong")?.textContent ?? "";
    const match = /^(\d{4})年(\d{2})月$/.exec(monthLabel);
    expect(match).not.toBeNull();
    const nextMonth = new Date(Number(match?.[1]), Number(match?.[2]), 15);
    const nextDate = `${nextMonth.getFullYear()}-${String(nextMonth.getMonth() + 1).padStart(2, "0")}-15`;

    fireEvent.click(screen.getByRole("button", { name: "下个月" }));
    fireEvent.click(await screen.findByRole("button", { name: nextDate }));
    expect(screen.getByRole("button", { name: "提醒日期" })).toHaveTextContent(nextDate);

    fireEvent.click(screen.getByRole("button", { name: "提醒日期" }));
    fireEvent.keyDown(screen.getByRole("dialog", { name: "选择日期" }), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "选择日期" })).not.toBeInTheDocument();
  });

  it("时间选择器以 24 小时制提供完整分钟精度", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => response(page([]))),
    );
    renderReminderApp();
    await screen.findByText("还没有提醒");
    fireEvent.click(screen.getByRole("button", { name: "新建提醒" }));
    fireEvent.click(screen.getByRole("button", { name: "提醒时间" }));

    const dialog = await screen.findByRole("dialog", { name: "选择提醒时间" });
    fireEvent.click(
      within(screen.getByRole("listbox", { name: "小时" })).getByRole("option", { name: "18" }),
    );
    fireEvent.click(
      within(screen.getByRole("listbox", { name: "分钟" })).getByRole("option", { name: "42" }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "完成" }));

    expect(screen.getByRole("button", { name: "提醒时间" })).toHaveTextContent("18:42");
    expect(screen.queryByRole("dialog", { name: "选择提醒时间" })).not.toBeInTheDocument();
  });

  it("按 offset 加载更多提醒", async () => {
    const first = makeReminder("373284764594991101", "第一条提醒");
    const second = makeReminder("373284764594991102", "第二条提醒");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      const offset = Number(url.searchParams.get("offset"));
      return response(page(offset === 0 ? [first] : [second], 2, offset));
    });
    vi.stubGlobal("fetch", fetchMock);

    renderReminderApp();
    expect(await screen.findByRole("heading", { name: "第一条提醒" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "加载更多提醒" }));

    expect(await screen.findByRole("heading", { name: "第二条提醒" })).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("offset=1");
  });

  it("保留提醒编辑路径和更新 API", async () => {
    let saved = makeReminder("373284764594991103", "原提醒");
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      if (path.startsWith("/api/v1/reminders?") && init?.method !== "PUT") {
        return response(page([saved]));
      }
      if (path === `/api/v1/reminders/${saved.id}` && init?.method === "PUT") {
        const payload = JSON.parse(String(init.body)) as { title: string };
        saved = { ...saved, title: payload.title, version: saved.version + 1 };
        return response(saved);
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderReminderApp();
    await screen.findByRole("heading", { name: "原提醒" });
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    fireEvent.change(screen.getByLabelText("标题"), { target: { value: "修改后的提醒" } });
    fireEvent.click(screen.getByRole("button", { name: "保存提醒" }));

    expect(await screen.findByRole("heading", { name: "修改后的提醒" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      `/api/v1/reminders/${saved.id}`,
      expect.objectContaining({ method: "PUT" }),
    );
  });
});

function renderReminderApp() {
  return render(
    <ToastProvider>
      <ReminderRouteHarness />
    </ToastProvider>,
  );
}

function ReminderRouteHarness() {
  const [pathname, setPathname] = useState<PlatformRoute>(platformPaths.reminders);
  const onNavigate = async (path: PlatformRoute) => {
    setPathname(path);
  };
  return (
    <ReminderPage
      key={pathname}
      mode={pathname === platformPaths.reminderCreate ? "create" : "list"}
      onNavigate={onNavigate}
    />
  );
}

function page(items: Reminder[], total = items.length, offset = 0) {
  return { items, total, limit: 100, offset };
}

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

function makeReminder(id: string, title: string, overrides: Partial<Reminder> = {}): Reminder {
  const scheduled = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000);
  return {
    id,
    title,
    content: "提醒内容。",
    repeat_type: "once",
    repeat_config: {},
    timezone: "UTC",
    next_run_at: scheduled.toISOString(),
    end_date: null,
    status: "active",
    version: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}
