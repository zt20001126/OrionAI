import { useEffect, useId, useState, type FormEvent } from "react";

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
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "success";
      items: ReminderExecution[];
      total: number;
    }
  | { status: "error"; message: string };

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

const EXECUTION_STATUS_MARKS: Record<ReminderExecutionStatus, string> = {
  pending: "○",
  sending: "↻",
  retry_wait: "↻",
  accepted: "✓",
  failed: "!",
  cancelled: "—",
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
  const [expandedReminderId, setExpandedReminderId] = useState<string | null>(null);

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

  const currentLoadState =
    loadState.status === "loading" || loadState.requestVersion !== reloadVersion
      ? { status: "loading" as const }
      : loadState;
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
    setExpandedReminderId(null);
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

  function toggleHistory(reminderId: string) {
    setExpandedReminderId((currentId) => (currentId === reminderId ? null : reminderId));
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
            className="reminders-back-link"
            disabled={isSaving}
            onClick={leaveCreatePage}
            type="button"
          >
            <PlatformIcon name="arrow" size={16} />
            返回提醒列表
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
          <div className="reminders-list" role="list">
            {reminders.map((reminder) => (
              <ReminderListItem
                busy={busyReminderId === reminder.id}
                expanded={expandedReminderId === reminder.id}
                key={reminder.id}
                onCancel={() => void handleCancel(reminder)}
                onEdit={() => openEditForm(reminder)}
                onToggleHistory={() => toggleHistory(reminder.id)}
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

    </div>
  );
}

interface ReminderListItemProps {
  busy: boolean;
  expanded: boolean;
  onCancel: () => void;
  onEdit: () => void;
  onToggleHistory: () => void;
  onPause: () => void;
  onResume: () => void;
  reminder: Reminder;
}

/** 单条提醒及其历史共用一个列表项，历史请求和结果按提醒隔离。 */
function ReminderListItem({
  busy,
  expanded,
  onCancel,
  onEdit,
  onToggleHistory,
  onPause,
  onResume,
  reminder,
}: ReminderListItemProps) {
  const historyPanelId = useId();
  const [historyState, setHistoryState] = useState<HistoryLoadState>({ status: "idle" });
  const [retryVersion, setRetryVersion] = useState(0);

  function toggleHistory() {
    if (!expanded) setHistoryState({ status: "loading" });
    onToggleHistory();
  }

  function retryHistory() {
    setHistoryState({ status: "loading" });
    setRetryVersion((version) => version + 1);
  }

  useEffect(() => {
    if (!expanded) return;
    const controller = new AbortController();
    listReminderExecutions(reminder.id, controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        setHistoryState({ status: "success", items: response.items, total: response.total });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHistoryState({
          status: "error",
          message: error instanceof Error ? error.message : "执行历史加载失败，请稍后重试。",
        });
      });
    return () => controller.abort();
  }, [expanded, reminder.id, retryVersion]);

  const currentHistoryState =
    expanded && historyState.status === "idle" ? { status: "loading" as const } : historyState;

  const statusClass = `reminder-status reminder-status--${reminder.status}`;
  const nextRun = formatNextRun(reminder);
  return (
    <div className="reminder-list-item" role="listitem">
      <article className="reminder-row">
        <div className="reminder-row__main">
          <div className="reminder-row__title-line">
            <h3>{reminder.title}</h3>
            <span className={statusClass}>{STATUS_LABELS[reminder.status]}</span>
          </div>
          <p className="reminder-row__content">{reminder.content}</p>
          <div className="reminder-row__meta">
            <span>{REPEAT_LABELS[reminder.repeat_type]}</span>
            {nextRun && <span>{nextRun}</span>}
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
          <button
            aria-controls={historyPanelId}
            aria-expanded={expanded}
            className="button button--secondary"
            onClick={toggleHistory}
            type="button"
          >
            {expanded ? "收起历史" : "执行历史"}
          </button>
        </div>
      </article>

      <div
        aria-hidden={!expanded}
        aria-labelledby={`${historyPanelId}-title`}
        className={`reminder-history-disclosure${expanded ? " is-expanded" : ""}`}
        id={historyPanelId}
        inert={!expanded}
        role="region"
      >
        <div className="reminder-history-disclosure__clip">
          <div className="reminder-history-panel">
            <div className="reminder-history-panel__heading">
              <h4 id={`${historyPanelId}-title`}>执行历史</h4>
              {currentHistoryState.status === "success" && (
                <span>
                  {currentHistoryState.total > currentHistoryState.items.length
                    ? `显示最近 ${currentHistoryState.items.length} 条，共 ${currentHistoryState.total} 条`
                    : `${currentHistoryState.items.length} 条记录`}
                </span>
              )}
            </div>
            {currentHistoryState.status === "idle" || currentHistoryState.status === "loading" ? (
              <div className="reminder-history-feedback" role="status">
                正在加载执行历史…
              </div>
            ) : currentHistoryState.status === "error" ? (
              <div className="reminder-history-feedback reminder-history-feedback--error" role="alert">
                <span>{currentHistoryState.message}</span>
                <button
                  className="button button--secondary"
                  onClick={retryHistory}
                  type="button"
                >
                  重试
                </button>
              </div>
            ) : currentHistoryState.items.length === 0 ? (
              <div className="reminder-history-feedback" role="status">
                还没有执行记录。
              </div>
            ) : (
              <div className="reminder-history-list">
                {currentHistoryState.items.map((execution) => (
                  <ExecutionRow
                    execution={execution}
                    key={execution.id}
                    timezone={reminder.timezone}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** 单条执行记录，展示计划时刻、SMTP 状态、重试次数和安全错误摘要。 */
function ExecutionRow({ execution, timezone }: { execution: ReminderExecution; timezone: string }) {
  return (
    <article className="reminder-execution-row">
      <div className="reminder-execution-row__summary">
        <span
          aria-hidden="true"
          className={`reminder-execution-status-mark reminder-execution-status-mark--${execution.status}`}
        >
          {EXECUTION_STATUS_MARKS[execution.status]}
        </span>
        <strong className={`reminder-execution-status reminder-execution-status--${execution.status}`}>
          {EXECUTION_STATUS_LABELS[execution.status]}
        </strong>
        <span>
          <small>计划执行时间</small>
          <time dateTime={execution.scheduled_at}>{formatDateTime(execution.scheduled_at, timezone)}</time>
        </span>
      </div>
      <div className="reminder-execution-row__details">
        <span>
          <small>实际开始</small>
          {execution.started_at ? (
            <time dateTime={execution.started_at}>{formatDateTime(execution.started_at, timezone)}</time>
          ) : (
            "尚未开始"
          )}
        </span>
        <span>
          <small>实际结束</small>
          {execution.finished_at ? (
            <time dateTime={execution.finished_at}>{formatDateTime(execution.finished_at, timezone)}</time>
          ) : (
            execution.started_at ? "执行中" : "尚未开始"
          )}
        </span>
        <span>
          <small>收件邮箱</small>
          {execution.recipient_email_masked ?? "未记录"}
        </span>
        <span>
          <small>重试次数</small>
          {execution.retry_count} 次
        </span>
      </div>
      {execution.error_message && (
        <p className="reminder-execution-row__error">失败原因：{execution.error_message}</p>
      )}
    </article>
  );
}

function formatNextRun(reminder: Reminder): string | null {
  if (reminder.status === "completed" && reminder.repeat_type === "once") return null;
  if (!reminder.next_run_at) return "暂无下一次计划";
  return `下次执行 ${formatDateTime(reminder.next_run_at, reminder.timezone)} · ${reminder.timezone}`;
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
