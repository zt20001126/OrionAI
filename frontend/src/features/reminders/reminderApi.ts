/** 提醒 API 类型与 Cookie 请求封装，集中管理管理页使用的 REST 路径。 */

import { getSafeErrorDetail } from "../../utils/safeErrorMessage";

export type ReminderRepeatType = "once" | "daily" | "weekly" | "monthly";
export type ReminderStatus = "active" | "paused" | "cancelled" | "completed";
export type ReminderExecutionStatus =
  | "pending"
  | "sending"
  | "retry_wait"
  | "accepted"
  | "failed"
  | "cancelled";

/** 当前用户的一条提醒规则及下次计划。 */
export interface Reminder {
  id: string;
  title: string;
  content: string;
  repeat_type: ReminderRepeatType;
  repeat_config: Record<string, string | number>;
  timezone: string;
  next_run_at: string | null;
  end_date: string | null;
  status: ReminderStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

/** 创建和完整更新提醒时提交的用户可编辑字段。 */
export interface ReminderScheduleInput {
  title: string;
  content: string;
  repeat_type: ReminderRepeatType;
  timezone: string;
  date?: string;
  start_date?: string;
  local_time: string;
  end_date?: string | null;
}

/** 执行历史中仅包含脱敏收件邮箱和安全错误摘要。 */
export interface ReminderExecution {
  id: string;
  scheduled_at: string;
  status: ReminderExecutionStatus;
  retry_count: number;
  next_retry_at: string | null;
  recipient_email_masked: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

interface PageResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

async function requestReminderApi<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "include",
      ...init,
    });
  } catch {
    throw new Error("网络连接异常，请检查网络后重试。");
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload.detail as unknown)
        : null;
    throw new Error(getErrorMessage(detail, response.status));
  }
  return payload as T;
}

function getErrorMessage(detail: unknown, status: number): string {
  if (status === 401) return "登录状态已失效，请刷新页面后重新登录。";
  if (status === 404) return "提醒不存在或当前不可用。";
  if (status === 409) return getSafeErrorDetail(detail, "提醒已发生变化，请刷新后重试。");
  if (status === 422) return getSafeErrorDetail(detail, "请检查提醒时间和填写内容。");
  if (status >= 500) return "提醒服务暂时不可用，请稍后重试。";
  return getSafeErrorDetail(detail, "提醒请求失败，请稍后重试。");
}

/** 查询当前用户的提醒列表。 */
export async function listReminders(
  options: { offset?: number; signal?: AbortSignal } = {},
): Promise<PageResponse<Reminder>> {
  const query = new URLSearchParams({ limit: "100", offset: String(options.offset ?? 0) });
  return requestReminderApi<PageResponse<Reminder>>(`/api/v1/reminders?${query}`, {
    signal: options.signal,
  });
}

/** 创建一条提醒规则。 */
export function createReminder(input: ReminderScheduleInput): Promise<Reminder> {
  return requestReminderApi<Reminder>("/api/v1/reminders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/** 使用读取时的 version 完整替换提醒规则。 */
export function updateReminder(
  reminderId: string,
  input: ReminderScheduleInput,
  expectedVersion: number,
): Promise<Reminder> {
  return requestReminderApi<Reminder>(`/api/v1/reminders/${reminderId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, expected_version: expectedVersion }),
  });
}

/** 暂停周期提醒。 */
export function pauseReminder(reminderId: string): Promise<Reminder> {
  return changeReminderState(reminderId, "pause");
}

/** 恢复周期提醒。 */
export function resumeReminder(reminderId: string): Promise<Reminder> {
  return changeReminderState(reminderId, "resume");
}

/** 软取消提醒并保留执行历史。 */
export function cancelReminder(reminderId: string): Promise<Reminder> {
  return changeReminderState(reminderId, "cancel");
}

/** 查询一条提醒的最近执行记录。 */
export async function listReminderExecutions(
  reminderId: string,
  signal?: AbortSignal,
): Promise<PageResponse<ReminderExecution>> {
  const query = new URLSearchParams({ limit: "20", offset: "0" });
  return requestReminderApi<PageResponse<ReminderExecution>>(
    `/api/v1/reminders/${reminderId}/executions?${query}`,
    { signal },
  );
}

function changeReminderState(
  reminderId: string,
  action: "pause" | "resume" | "cancel",
): Promise<Reminder> {
  return requestReminderApi<Reminder>(`/api/v1/reminders/${reminderId}/${action}`, {
    method: "POST",
  });
}
