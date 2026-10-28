import { useEffect, useState, type FormEvent } from "react";

import { useToast } from "../../components/ToastProvider";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { PlatformIcon } from "../platform/PlatformIcon";
import {
  buildReminderScheduleInput,
  createDefaultReminderForm,
  ReminderForm,
  reminderFormFromReminder,
  validateReminderForm,
  type ReminderFormValues,
} from "./ReminderForm";
import {
  cancelReminder,
  createReminder,
  listReminderExecutions,
  listReminders,
  pauseReminder,
  resumeReminder,
  updateReminder,
  type Reminder,
  type ReminderExecution,
  type ReminderExecutionStatus,
  type ReminderRepeatType,
} from "./reminderApi";
import "./reminders.css";

interface ReminderPageProps {
  mode: "list" | "create";
  onNavigate: (path: PlatformRoute, replace?: boolean) => Promise<void> | void;
}

type ReminderLoadState =
  | { status: "loading" }
  | { status: "success"; requestVersion: number; items: Reminder[]; total: number }
  | { status: "error"; requestVersion: number; message: string };

type HistoryLoadState =
  | { status: "loading" }
  | {
      status: "success";
      reminderId: string;
      items: ReminderExecution[];
      total: number;
    }
  | { status: "error"; reminderId: string; message: string };

interface HistorySelection {
  reminderId: string;
  title: string;
  timezone: string;
}

const REPEAT_LABELS: Record<ReminderRepeatType, string> = {
  once: "单次",
  daily: "每天",
  weekly: "每周",
  monthly: "每月",
};

const STATUS_LABELS: Record<Reminder["status"], string> = {
  active: "进行中",
  paused: "已暂停",
  cancelled: "已取消",
  completed: "已完成",
};

const EXECUTION_STATUS_LABELS: Record<ReminderExecutionStatus, string> = {
  pending: "等待发送",
  sending: "发送中",
  retry_wait: "等待重试",
  accepted: "邮件服务已接受",
  failed: "发送失败",
  cancelled: "未发送",
};

/** 提醒助手列表与独立新建路由，共用编辑、执行历史和 API 状态。 */
export function ReminderPage({ mode, onNavigate }: ReminderPageProps) {
  const { confirm, showToast } = useToast();
  const isCreatePage = mode === "create";
  const [reloadVersion, setReloadVersion] = useState(0);
  const [loadState, setLoadState] = useState<ReminderLoadState>({ status: "loading" });
  const [formMode, setFormMode] = useState<"edit" | null>(null);
  const [editingReminder, setEditingReminder] = useState<Reminder | null>(null);
  const [form, setForm] = useState<ReminderFormValues>(createDefaultReminderForm);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [busyReminderId, setBusyReminderId] = useState<string | null>(null);
  const [historySelection, setHistorySelection] = useState<HistorySelection | null>(null);
  const [historyState, setHistoryState] = useState<HistoryLoadState>({ status: "loading" });

  useEffect(() => {
    if (isCreatePage) return;
    const controller = new AbortController();
    listReminders({ signal: controller.signal })
      .then((response) => {
        if (controller.signal.aborted) return;
        setLoadState({
          status: "success",
          requestVersion: reloadVersion,
          items: response.items,
          total: response.total,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setLoadState({
          status: "error",
          requestVersion: reloadVersion,
          message: error instanceof Error ? error.message : "提醒列表加载失败，请稍后重试。",
        });
      });
    return () => controller.abort();
  }, [isCreatePage, reloadVersion]);

  useEffect(() => {
    if (!historySelection) return;
    const controller = new AbortController();
    listReminderExecutions(historySelection.reminderId, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        setHistoryState({
          status: "success",
          reminderId: historySelection.reminderId,
          items: response.items,
          total: response.total,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHistoryState({
          status: "error",
          reminderId: historySelection.reminderId,
          message: error instanceof Error ? error.message : "执行历史加载失败，请稍后重试。",
        });
      });
    return () => controller.abort();
  }, [historySelection]);

  const currentLoadState =
    loadState.status === "loading" || loadState.requestVersion !== reloadVersion
      ? { status: "loading" as const }
      : loadState;
  const currentHistoryState =
    !historySelection ||
    historyState.status === "loading" ||
    historyState.reminderId !== historySelection.reminderId
      ? { status: "loading" as const }
      : historyState;
  const reminders = currentLoadState.status === "success" ? currentLoadState.items : [];
  const isEmpty = currentLoadState.status === "success" && currentLoadState.items.length === 0;
  const allowedPastDate =
    formMode === "edit" &&
    editingReminder &&
    form.repeatType === editingReminder.repeat_type &&
    form.repeatType !== "once"
      ? String(editingReminder.repeat_config.start_date ?? "")
      : undefined;
  function openCreateForm() {
    setHistorySelection(null);
    void onNavigate(platformPaths.reminderCreate);
  }

  function openEditForm(reminder: Reminder) {
    setEditingReminder(reminder);
    setForm(reminderFormFromReminder(reminder));
    setFormMode("edit");
    setFormError(null);
  }

  function closeForm() {
    setFormMode(null);
    setEditingReminder(null);
    setFormError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSaving) return;
    const validationError = validateReminderForm(form, new Date(), allowedPastDate);
    if (validationError) {
      setFormError(validationError);
      showToast("error", validationError);
      return;
    }
    setIsSaving(true);
    setFormError(null);
    try {
      const payload = buildReminderScheduleInput(form);
      if (formMode === "edit" && editingReminder) {
        await updateReminder(editingReminder.id, payload, editingReminder.version);
        showToast("success", "提醒已更新。");
      } else {
        await createReminder(payload);
        showToast("success", "提醒已创建。");
      }
      if (isCreatePage) {
        await onNavigate(platformPaths.reminders, true);
      } else {
        closeForm();
        setReloadVersion((version) => version + 1);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "提醒保存失败，请检查填写内容。";
      showToast("error", message);
    } finally {
      setIsSaving(false);
    }
  }

  async function handlePause(reminder: Reminder) {
    await runReminderAction(reminder.id, "提醒已暂停。", () => pauseReminder(reminder.id));
  }

  async function handleResume(reminder: Reminder) {
    await runReminderAction(reminder.id, "提醒已恢复。", () => resumeReminder(reminder.id));
  }

  async function handleCancel(reminder: Reminder) {
    const accepted = await confirm({
      title: "取消这条提醒？",
      description: "尚未开始发送的计划会停止，已有执行历史仍会保留。",
      cancelLabel: "继续保留",
      confirmLabel: "取消提醒",
      tone: "danger",
      onConfirm: async () => {
        await runReminderAction(reminder.id, "提醒已取消。", () => cancelReminder(reminder.id));
      },
    });
    if (!accepted) return;
  }

  async function runReminderAction(
    reminderId: string,
    successMessage: string,
    action: () => Promise<Reminder>,
  ) {
    setBusyReminderId(reminderId);
    try {
      await action();
      showToast("success", successMessage);
      setReloadVersion((version) => version + 1);
    } catch (error) {
      showToast("error", error instanceof Error ? error.message : "提醒操作失败，请稍后重试。");
      throw error;
    } finally {
      setBusyReminderId(null);
    }
  }

  function openHistory(reminder: Reminder) {
    setHistorySelection({
      reminderId: reminder.id,
      title: reminder.title,
      timezone: reminder.timezone,
    });
  }

  async function handleLoadMoreReminders() {
    if (currentLoadState.status !== "success" || isLoadingMore) return;
    setIsLoadingMore(true);
    setLoadMoreError(null);
    try {
      const response = await listReminders({ offset: currentLoadState.items.length });
      setLoadState((current) => {
        if (current.status !== "success" || current.requestVersion !== reloadVersion) {
          return current;
        }
        return {
          ...current,
          items: [...current.items, ...response.items],
          total: response.total,
        };
      });
    } catch (error) {
      setLoadMoreError(error instanceof Error ? error.message : "加载更多提醒失败，请稍后重试。");
    } finally {
      setIsLoadingMore(false);
    }
  }

  function updateForm(values: ReminderFormValues) {
    setForm(values);
    if (formError) setFormError(null);
  }

  const listSummary =
    currentLoadState.status === "success" ? `${currentLoadState.total} 条提醒` : "";

  if (isCreatePage) {
    function leaveCreatePage() {
      if (isSaving) return;
      setFormError(null);
      void onNavigate(platformPaths.reminders, true);
    }

    return (
      <div className="reminders-page reminders-page--create">
        <header className="reminders-create-heading">
          <button
            aria-label="返回我的提醒"
            className="button button--outline reminders-back-button"
            disabled={isSaving}
            onClick={leaveCreatePage}
            type="button"
          >
            <PlatformIcon name="arrow" size={16} />
            返回
          </button>
          <h1 id="reminder-page-title">新建提醒</h1>
        </header>
        <section aria-labelledby="reminder-page-title" className="reminder-editor">
          <ReminderForm
            error={formError}
            isSaving={isSaving}
            mode="create"
            onCancel={leaveCreatePage}
            onChange={updateForm}
            onSubmit={(submitEvent) => void handleSubmit(submitEvent)}
            values={form}
          />
        </section>
      </div>
    );
  }

  return (
    <div className="reminders-page">
      <header className="reminders-heading">
        <div>
          <h1>提醒助手</h1>
          <p>按计划将提醒发送到当前账号邮箱。</p>
        </div>
        <button className="button button--primary" onClick={openCreateForm} type="button">
          <PlatformIcon name="plus" size={18} />
          新建提醒
        </button>
      </header>

      <section aria-labelledby="reminders-list-title" className="reminders-section">
        <div className="reminders-section__heading">
          <h2 id="reminders-list-title">我的提醒</h2>
          <span>{listSummary}</span>
        </div>

        {currentLoadState.status === "loading" ? (
          <div className="reminders-message" role="status">
            正在加载提醒…
          </div>
        ) : currentLoadState.status === "error" ? (
          <div className="reminders-message reminders-message--error" role="alert">
            <strong>提醒列表加载失败</strong>
            <span>{currentLoadState.message}</span>
            <button
              className="button button--outline"
              onClick={() => setReloadVersion((version) => version + 1)}
              type="button"
            >
              重试
            </button>
          </div>
        ) : isEmpty ? (
          <div className="reminders-message" role="status">
            <strong>还没有提醒</strong>
            <span>创建一条提醒，系统会在计划时间发送邮件到当前账号邮箱。</span>
            <button className="button button--outline" onClick={openCreateForm} type="button">
              创建第一条提醒
            </button>
          </div>
        ) : (
          <div className="reminders-list">
            {reminders.map((reminder) => (
              <ReminderRow
                busy={busyReminderId === reminder.id}
                key={reminder.id}
                onCancel={() => void handleCancel(reminder)}
                onEdit={() => openEditForm(reminder)}
                onHistory={() => openHistory(reminder)}
                onPause={() => void handlePause(reminder)}
                onResume={() => void handleResume(reminder)}
                reminder={reminder}
              />
            ))}
          </div>
        )}
        {currentLoadState.status === "success" &&
          currentLoadState.items.length < currentLoadState.total && (
            <div className="reminders-load-more">
              {loadMoreError && <span role="alert">{loadMoreError}</span>}
              <button
                className="button button--outline"
                disabled={isLoadingMore}
                onClick={() => void handleLoadMoreReminders()}
                type="button"
              >
                {isLoadingMore ? "加载中…" : "加载更多提醒"}
              </button>
            </div>
          )}
      </section>

      {formMode === "edit" && (
        <section aria-labelledby="reminder-form-title" className="reminder-edit-section">
          <div className="reminders-section__heading">
            <h2 id="reminder-form-title">编辑提醒</h2>
            <button className="button button--outline" onClick={closeForm} type="button">
              关闭
            </button>
          </div>
          <ReminderForm
            allowPastDate={allowedPastDate}
            error={formError}
            isSaving={isSaving}
            mode="edit"
            onCancel={closeForm}
            onChange={updateForm}
            onSubmit={(submitEvent) => void handleSubmit(submitEvent)}
            values={form}
          />
        </section>
      )}

      {historySelection && (
        <section aria-labelledby="reminder-history-title" className="reminder-history-section">
          <div className="reminders-section__heading">
            <div>
              <h2 id="reminder-history-title">执行历史</h2>
              <p>{historySelection.title}</p>
            </div>
            <button
              className="button button--outline"
              onClick={() => setHistorySelection(null)}
              type="button"
            >
              收起历史
            </button>
          </div>
          {currentHistoryState.status === "loading" ? (
            <div className="reminders-message" role="status">
              正在加载执行历史…
            </div>
          ) : currentHistoryState.status === "error" ? (
            <div className="reminders-message reminders-message--error" role="alert">
              <span>{currentHistoryState.message}</span>
              <button
                className="button button--outline"
                onClick={() => setHistorySelection({ ...historySelection })}
                type="button"
              >
                重试
              </button>
            </div>
          ) : currentHistoryState.items.length === 0 ? (
            <div className="reminders-message" role="status">
              还没有执行记录。
            </div>
          ) : (
            <div className="reminder-history-list">
              {currentHistoryState.items.map((execution) => (
                <ExecutionRow
                  execution={execution}
                  key={execution.id}
                  timezone={historySelection.timezone}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

interface ReminderRowProps {
  busy: boolean;
  onCancel: () => void;
  onEdit: () => void;
  onHistory: () => void;
  onPause: () => void;
  onResume: () => void;
  reminder: Reminder;
}

/** 单条提醒列表行，根据状态展示可执行的管理动作。 */
function ReminderRow({
  busy,
  onCancel,
  onEdit,
  onHistory,
  onPause,
  onResume,
  reminder,
}: ReminderRowProps) {
  const statusClass = `reminder-status reminder-status--${reminder.status}`;
  return (
    <article className="reminder-row">
      <div className="reminder-row__main">
        <div className="reminder-row__title-line">
          <h3>{reminder.title}</h3>
          <span className={statusClass}>{STATUS_LABELS[reminder.status]}</span>
        </div>
        <p className="reminder-row__content">{reminder.content}</p>
        <div className="reminder-row__meta">
          <span>{REPEAT_LABELS[reminder.repeat_type]}</span>
          <span>{formatNextRun(reminder)}</span>
        </div>
      </div>
      <div className="reminder-row__actions">
        {(reminder.status === "active" || reminder.status === "paused") && (
          <button className="button button--outline" disabled={busy} onClick={onEdit} type="button">
            编辑
          </button>
        )}
        {reminder.status === "active" && reminder.repeat_type !== "once" && (
          <button
            className="button button--outline"
            disabled={busy}
            onClick={onPause}
            type="button"
          >
            暂停
          </button>
        )}
        {reminder.status === "paused" && (
          <button
            className="button button--outline"
            disabled={busy}
            onClick={onResume}
            type="button"
          >
            恢复
          </button>
        )}
        {(reminder.status === "active" || reminder.status === "paused") && (
          <button
            className="button button--outline"
            disabled={busy}
            onClick={onCancel}
            type="button"
          >
            取消
          </button>
        )}
        <button className="button button--secondary" onClick={onHistory} type="button">
          执行历史
        </button>
      </div>
    </article>
  );
}

/** 单条执行记录，展示计划时刻、SMTP 状态、重试次数和安全错误摘要。 */
function ExecutionRow({ execution, timezone }: { execution: ReminderExecution; timezone: string }) {
  return (
    <article className="reminder-execution-row">
      <div>
        <strong>{EXECUTION_STATUS_LABELS[execution.status]}</strong>
        <span>{formatDateTime(execution.scheduled_at, timezone)}</span>
      </div>
      <div>
        <span>重试 {execution.retry_count} 次</span>
        {execution.recipient_email_masked && <span>{execution.recipient_email_masked}</span>}
        {execution.error_message && (
          <span className="reminder-execution-row__error">{execution.error_message}</span>
        )}
      </div>
      <small>
        {execution.started_at
          ? `开始 ${formatDateTime(execution.started_at, timezone)}`
          : "尚未开始发送"}
        {execution.finished_at ? ` · 结束 ${formatDateTime(execution.finished_at, timezone)}` : ""}
      </small>
    </article>
  );
}

function formatNextRun(reminder: Reminder): string {
  if (!reminder.next_run_at) return "暂无下一次计划";
  return `${formatDateTime(reminder.next_run_at, reminder.timezone)} · ${reminder.timezone}`;
}

function formatDateTime(value: string, timezone?: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    ...(timezone ? { timeZone: timezone } : {}),
  }).format(new Date(value));
}
