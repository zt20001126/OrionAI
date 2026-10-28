import type { FormEvent } from "react";

import { PlatformIcon } from "../platform/PlatformIcon";
import {
  ReminderDatePicker,
  ReminderSelect,
  ReminderTimePicker,
  ReminderTimezoneSelect,
} from "./ReminderFormControls";
import type { Reminder, ReminderRepeatType, ReminderScheduleInput } from "./reminderApi";

export interface ReminderFormValues {
  title: string;
  content: string;
  repeatType: ReminderRepeatType;
  date: string;
  startDate: string;
  localTime: string;
  endDate: string;
  timezone: string;
}

interface ReminderFormProps {
  allowPastDate?: string;
  error: string | null;
  isSaving: boolean;
  mode: "create" | "edit";
  onCancel: () => void;
  onChange: (values: ReminderFormValues) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  values: ReminderFormValues;
}

const REPEAT_OPTIONS = [
  { value: "once", label: "单次提醒" },
  { value: "daily", label: "每天重复" },
  { value: "weekly", label: "每周重复" },
  { value: "monthly", label: "每月重复" },
] as const;

/** 新建与编辑共用的表单布局，不改变 reminders API 输入结构。 */
export function ReminderForm({
  allowPastDate,
  error,
  isSaving,
  mode,
  onCancel,
  onChange,
  onSubmit,
  values,
}: ReminderFormProps) {
  const today = getDateInTimezone(new Date(), values.timezone);
  const activeDate = values.repeatType === "once" ? values.date : values.startDate;
  const minimumPlanDate = allowPastDate === activeDate && activeDate < today ? activeDate : today;
  const titleInvalid = Boolean(error?.includes("标题"));
  const contentInvalid = Boolean(error?.includes("内容"));
  const dateInvalid = Boolean(error?.includes("日期"));
  const endDateInvalid = Boolean(error?.includes("结束日期"));
  const timeInvalid = Boolean(error?.includes("时间"));
  const timezoneInvalid = Boolean(error?.includes("时区"));

  function changeField<K extends keyof ReminderFormValues>(key: K, value: ReminderFormValues[K]) {
    onChange({ ...values, [key]: value });
  }

  function changeRepeatType(value: string) {
    const repeatType = value as ReminderRepeatType;
    const currentPlanDate = values.repeatType === "once" ? values.date : values.startDate;
    onChange({
      ...values,
      repeatType,
      date: currentPlanDate,
      startDate: currentPlanDate,
    });
  }

  return (
    <form className="reminder-form" noValidate onSubmit={onSubmit}>
      <fieldset
        className="reminder-form-fields"
        disabled={isSaving}
        key={isSaving ? "saving" : "ready"}
      >
        <label className="reminder-field reminder-field--wide">
          <span>标题</span>
          <input
            aria-invalid={titleInvalid || undefined}
            autoComplete="off"
            maxLength={120}
            onChange={(event) => changeField("title", event.target.value)}
            required
            value={values.title}
          />
        </label>

        <label className="reminder-field reminder-field--wide">
          <span>内容</span>
          <textarea
            aria-invalid={contentInvalid || undefined}
            maxLength={5000}
            onChange={(event) => changeField("content", event.target.value)}
            required
            rows={3}
            value={values.content}
          />
        </label>

        <div className="reminder-field">
          <span>重复方式</span>
          <ReminderSelect
            disabled={isSaving}
            label="重复方式"
            onChange={changeRepeatType}
            options={[...REPEAT_OPTIONS]}
            value={values.repeatType}
          />
        </div>

        <div className="reminder-field">
          <span>{values.repeatType === "once" ? "提醒日期" : "开始日期"}</span>
          <ReminderDatePicker
            disabled={isSaving}
            invalid={dateInvalid}
            label={values.repeatType === "once" ? "提醒日期" : "开始日期"}
            minDate={minimumPlanDate}
            onChange={(value) => onChange({ ...values, date: value, startDate: value })}
            timezone={values.timezone}
            value={activeDate}
          />
        </div>

        {values.repeatType !== "once" && (
          <div className="reminder-field">
            <span>结束日期（可选）</span>
            <ReminderDatePicker
              disabled={isSaving}
              invalid={endDateInvalid}
              label="结束日期（可选）"
              minDate={values.startDate || today}
              onChange={(value) => changeField("endDate", value)}
              timezone={values.timezone}
              value={values.endDate}
            />
          </div>
        )}

        <div
          className={`reminder-field${values.repeatType === "once" ? " reminder-field--wide" : ""}`}
        >
          <span>提醒时间</span>
          <ReminderTimePicker
            disabled={isSaving}
            invalid={timeInvalid}
            label="提醒时间"
            onChange={(value) => changeField("localTime", value)}
            value={values.localTime}
          />
        </div>

        <div className="reminder-field reminder-field--wide">
          <span>时区</span>
          <ReminderTimezoneSelect
            disabled={isSaving}
            invalid={timezoneInvalid}
            onChange={(value) => changeField("timezone", value)}
            value={values.timezone}
          />
        </div>
      </fieldset>

      {values.repeatType === "weekly" && (
        <p className="reminder-form-note">每周按开始日期对应的星期重复。</p>
      )}
      {values.repeatType === "monthly" && (
        <p className="reminder-form-note">每月按开始日期的日号重复；当月份没有该日时会跳过。</p>
      )}
      {error && (
        <p className="reminder-form-error" role="alert">
          {error}
        </p>
      )}

      <div className="reminder-form-actions">
        <button
          className="button button--outline"
          disabled={isSaving}
          onClick={onCancel}
          type="button"
        >
          {mode === "create" ? "取消" : "返回"}
        </button>
        <button className="button button--primary" disabled={isSaving} type="submit">
          {isSaving && <span aria-hidden="true" className="button-spinner" />}
          {isSaving ? "保存中…" : "保存提醒"}
          {!isSaving && <PlatformIcon name="arrow" size={16} />}
        </button>
      </div>
    </form>
  );
}

export function createDefaultReminderForm(): ReminderFormValues {
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const localStart = new Date();
  localStart.setMinutes(localStart.getMinutes() + 10);
  const date = formatLocalDate(localStart);
  return {
    title: "",
    content: "",
    repeatType: "once",
    date,
    startDate: date,
    localTime: formatLocalTime(localStart),
    endDate: "",
    timezone,
  };
}

export function reminderFormFromReminder(reminder: Reminder): ReminderFormValues {
  const fallbackScheduledTime = new Date();
  fallbackScheduledTime.setMinutes(fallbackScheduledTime.getMinutes() + 10);
  const scheduledDate = reminder.next_run_at
    ? formatDateInTimezone(reminder.next_run_at, reminder.timezone)
    : formatDateInTimezone(fallbackScheduledTime, reminder.timezone);
  return {
    title: reminder.title,
    content: reminder.content,
    repeatType: reminder.repeat_type,
    date: scheduledDate,
    startDate: String(reminder.repeat_config.start_date ?? scheduledDate),
    localTime: String(
      reminder.repeat_config.local_time ??
        (reminder.next_run_at
          ? formatTimeInTimezone(reminder.next_run_at, reminder.timezone)
          : formatTimeInTimezone(fallbackScheduledTime, reminder.timezone)),
    ),
    endDate: reminder.end_date ?? "",
    timezone: reminder.timezone,
  };
}

export function buildReminderScheduleInput(values: ReminderFormValues): ReminderScheduleInput {
  const common = {
    title: values.title.trim(),
    content: values.content.trim(),
    repeat_type: values.repeatType,
    timezone: values.timezone,
    local_time: values.localTime,
  };
  if (values.repeatType === "once") return { ...common, date: values.date };
  return {
    ...common,
    start_date: values.startDate,
    ...(values.endDate ? { end_date: values.endDate } : {}),
  };
}

export function validateReminderForm(
  values: ReminderFormValues,
  now = new Date(),
  allowedPastDate?: string,
): string | null {
  if (!values.title.trim()) return "请填写提醒标题。";
  if (!values.content.trim()) return "请填写提醒内容。";
  if (!isValidTime(values.localTime)) return "请选择有效的提醒时间。";

  try {
    new Intl.DateTimeFormat("en-US", { timeZone: values.timezone });
  } catch {
    return "请选择有效的时区。";
  }

  const plannedDate = values.repeatType === "once" ? values.date : values.startDate;
  if (!isValidDate(plannedDate)) return "请选择有效的提醒日期。";
  const today = getDateInTimezone(now, values.timezone);
  if (plannedDate < today && plannedDate !== allowedPastDate) {
    return "提醒日期不能早于今天。";
  }
  if (values.repeatType === "once" && plannedDate === today) {
    const currentTime = formatTimeInTimezone(now, values.timezone);
    if (values.localTime <= currentTime) return "单次提醒时间必须晚于当前时间。";
  }

  if (values.repeatType !== "once" && values.endDate) {
    if (!isValidDate(values.endDate)) return "请选择有效的结束日期。";
    if (values.endDate < values.startDate) return "结束日期不能早于开始日期。";
  }
  return null;
}

function getDateInTimezone(value: Date, timezone: string): string {
  return formatDateInTimezone(value, timezone);
}

function formatDateInTimezone(value: string | Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: timezone,
    year: "numeric",
  }).formatToParts(typeof value === "string" ? new Date(value) : value);
  const dateParts = new Map(parts.map(({ type, value: partValue }) => [type, partValue]));
  return `${dateParts.get("year")}-${dateParts.get("month")}-${dateParts.get("day")}`;
}

function formatTimeInTimezone(value: string | Date, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: timezone,
  }).format(typeof value === "string" ? new Date(value) : value);
}

function formatLocalDate(value: Date): string {
  return `${value.getFullYear()}-${pad2(value.getMonth() + 1)}-${pad2(value.getDate())}`;
}

function formatLocalTime(value: Date): string {
  return `${pad2(value.getHours())}:${pad2(value.getMinutes())}`;
}

function isValidDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const [, year, month, day] = match;
  const parsed = new Date(Number(year), Number(month) - 1, Number(day));
  return (
    parsed.getFullYear() === Number(year) &&
    parsed.getMonth() === Number(month) - 1 &&
    parsed.getDate() === Number(day)
  );
}

function isValidTime(value: string): boolean {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  return Boolean(match && Number(match[1]) <= 23 && Number(match[2]) <= 59);
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}
