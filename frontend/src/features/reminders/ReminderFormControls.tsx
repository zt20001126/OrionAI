import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

import { PlatformIcon } from "../platform/PlatformIcon";

interface ReminderOption {
  label: string;
  value: string;
}

interface ReminderSelectProps {
  disabled?: boolean;
  invalid?: boolean;
  label: string;
  onChange: (value: string) => void;
  options: ReminderOption[];
  value: string;
}

/** 与提醒表单令牌一致、支持键盘的单选浮层。 */
export function ReminderSelect({
  disabled = false,
  invalid = false,
  label,
  onChange,
  options,
  value,
}: ReminderSelectProps) {
  const id = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(
    Math.max(
      0,
      options.findIndex((item) => item.value === value),
    ),
  );
  const isOpen = open && !disabled;
  const currentIndex = Math.max(
    0,
    options.findIndex((item) => item.value === value),
  );
  const selected = options[currentIndex];
  const popoverStyle = usePopoverPosition(isOpen, triggerRef, panelRef, true);
  const close = useCallback((restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  useDismiss(isOpen, triggerRef, panelRef, close);

  useEffect(() => {
    if (isOpen) optionRefs.current[activeIndex]?.focus();
  }, [activeIndex, isOpen]);

  function activate(index: number) {
    const boundedIndex = Math.max(0, Math.min(options.length - 1, index));
    setActiveIndex(boundedIndex);
    optionRefs.current[boundedIndex]?.focus();
  }

  function selectOption(option: ReminderOption) {
    onChange(option.value);
    close(true);
  }

  function handleTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
      event.preventDefault();
      setActiveIndex(currentIndex);
      setOpen(true);
    }
  }

  function handleListKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      activate(activeIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activate(activeIndex - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      activate(0);
    } else if (event.key === "End") {
      event.preventDefault();
      activate(options.length - 1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      const option = options[activeIndex];
      if (option) selectOption(option);
    } else if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "Tab") {
      close();
      moveFocusFromTrigger(triggerRef.current, event.shiftKey);
    } else if (event.key.length === 1 && /[a-z0-9]/i.test(event.key)) {
      const nextIndex = options.findIndex((item) =>
        item.label.toLocaleLowerCase().startsWith(event.key.toLocaleLowerCase()),
      );
      if (nextIndex >= 0) {
        event.preventDefault();
        activate(nextIndex);
      }
    }
  }

  return (
    <>
      <button
        aria-controls={id}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        aria-label={label}
        aria-invalid={invalid || undefined}
        className="reminder-select-trigger"
        disabled={disabled}
        onClick={() => {
          if (isOpen) close();
          else {
            setActiveIndex(currentIndex);
            setOpen(true);
          }
        }}
        onKeyDown={handleTriggerKeyDown}
        ref={triggerRef}
        type="button"
      >
        <span>{selected?.label ?? value}</span>
        <PlatformIcon name="chevron" size={16} />
      </button>
      {isOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="reminder-select-popover"
            id={id}
            aria-label={label}
            onKeyDown={handleListKeyDown}
            ref={panelRef}
            role="listbox"
            style={popoverStyle}
            tabIndex={-1}
          >
            {options.map((option, index) => (
              <button
                aria-selected={option.value === value}
                className="reminder-select-option"
                key={option.value}
                onClick={() => selectOption(option)}
                onFocus={() => setActiveIndex(index)}
                ref={(element) => {
                  optionRefs.current[index] = element;
                }}
                role="option"
                tabIndex={index === activeIndex ? 0 : -1}
                type="button"
              >
                <span>{option.label}</span>
                {option.value === value && <span aria-hidden="true">✓</span>}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}

interface ReminderDatePickerProps {
  disabled?: boolean;
  invalid?: boolean;
  label: string;
  minDate: string;
  onChange: (value: string) => void;
  timezone: string;
  value: string;
}

/** 以 ISO 日期值显示的日历选择器；日期面板挂载到 body，避免父级裁切。 */
export function ReminderDatePicker({
  disabled = false,
  invalid = false,
  label,
  minDate,
  onChange,
  timezone,
  value,
}: ReminderDatePickerProps) {
  const id = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [activeDate, setActiveDate] = useState(
    () => parseDate(value) ?? parseDate(minDate) ?? new Date(),
  );
  const [visibleMonth, setVisibleMonth] = useState(() =>
    firstOfMonth(parseDate(value) ?? parseDate(minDate) ?? new Date()),
  );
  const isOpen = open && !disabled;
  const popoverStyle = usePopoverPosition(isOpen, triggerRef, panelRef, false);
  const today = formatDateInTimezone(new Date(), timezone);
  const selectedDate = parseDate(value);
  const cells = getCalendarCells(visibleMonth);

  const close = useCallback((restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);
  useDismiss(isOpen, triggerRef, panelRef, close);

  useEffect(() => {
    if (!isOpen) return;
    const target = document.getElementById(`${id}-${formatDate(activeDate)}`);
    target?.focus();
  }, [activeDate, id, isOpen, visibleMonth]);

  function openCalendar() {
    const currentValue = selectedDate ? formatDate(selectedDate) : "";
    const initialDate =
      currentValue >= minDate
        ? (selectedDate ?? parseDate(minDate) ?? new Date())
        : (parseDate(minDate) ?? new Date());
    setActiveDate(initialDate);
    setVisibleMonth(firstOfMonth(initialDate));
    setOpen(true);
  }

  function shiftVisibleMonth(amount: number) {
    const nextMonth = addMonths(visibleMonth, amount);
    const lastDay = new Date(nextMonth.getFullYear(), nextMonth.getMonth() + 1, 0).getDate();
    const nextDate = new Date(
      nextMonth.getFullYear(),
      nextMonth.getMonth(),
      Math.min(activeDate.getDate(), lastDay),
    );
    const targetDate = formatDate(nextDate) < minDate ? (parseDate(minDate) ?? nextDate) : nextDate;
    setVisibleMonth(firstOfMonth(nextMonth));
    setActiveDate(targetDate);
  }

  function selectDate(date: Date) {
    const nextValue = formatDate(date);
    if (nextValue < minDate) return;
    onChange(nextValue);
    close(true);
  }

  function moveActiveDate(date: Date) {
    if (formatDate(date) < minDate) return;
    setActiveDate(date);
    setVisibleMonth(firstOfMonth(date));
  }

  function handleDateKeyDown(event: KeyboardEvent<HTMLButtonElement>, date: Date) {
    const keyDeltas: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
    };
    const delta = keyDeltas[event.key];
    if (delta !== undefined) {
      event.preventDefault();
      const nextDate = new Date(date);
      nextDate.setDate(nextDate.getDate() + delta);
      moveActiveDate(nextDate);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const nextDate = new Date(date);
      const weekday = nextDate.getDay();
      nextDate.setDate(nextDate.getDate() + (event.key === "Home" ? -weekday : 6 - weekday));
      moveActiveDate(nextDate);
    } else if (event.key === "PageUp" || event.key === "PageDown") {
      event.preventDefault();
      const nextDate = new Date(date);
      const nextMonth = addMonths(date, event.key === "PageUp" ? -1 : 1);
      const lastDay = new Date(nextMonth.getFullYear(), nextMonth.getMonth() + 1, 0).getDate();
      nextDate.setFullYear(
        nextMonth.getFullYear(),
        nextMonth.getMonth(),
        Math.min(date.getDate(), lastDay),
      );
      if (formatDate(nextDate) < minDate) return;
      moveActiveDate(nextDate);
    } else if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "Tab") {
      close();
      moveFocusFromTrigger(triggerRef.current, event.shiftKey);
    }
  }

  return (
    <>
      <button
        aria-controls={id}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-label={label}
        aria-invalid={invalid || undefined}
        className="reminder-picker-trigger"
        disabled={disabled}
        onClick={() => (isOpen ? close() : openCalendar())}
        ref={triggerRef}
        type="button"
      >
        <span>{value || "选择日期"}</span>
        <PlatformIcon name="calendar" size={17} />
      </button>
      {isOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            aria-label="选择日期"
            className="reminder-calendar-popover"
            id={id}
            onKeyDown={(event) => {
              if (event.defaultPrevented) return;
              if (event.key === "Escape") {
                event.preventDefault();
                close(true);
              } else if (event.key === "Tab") {
                event.preventDefault();
                close();
                moveFocusFromTrigger(triggerRef.current, event.shiftKey);
              }
            }}
            ref={panelRef}
            role="dialog"
            style={popoverStyle}
          >
            <div className="reminder-calendar-header">
              <button
                aria-label="上个月"
                className="reminder-calendar-nav"
                disabled={isPreviousMonthDisabled(visibleMonth, minDate)}
                onClick={() => shiftVisibleMonth(-1)}
                type="button"
              >
                ‹
              </button>
              <strong>{formatMonth(visibleMonth)}</strong>
              <button
                aria-label="下个月"
                className="reminder-calendar-nav"
                onClick={() => shiftVisibleMonth(1)}
                type="button"
              >
                ›
              </button>
            </div>
            <div aria-hidden="true" className="reminder-calendar-weekdays">
              {WEEKDAYS.map((weekday) => (
                <span key={weekday}>{weekday}</span>
              ))}
            </div>
            <div
              aria-label={formatMonth(visibleMonth)}
              className="reminder-calendar-grid"
              role="grid"
            >
              {Array.from({ length: cells.length / 7 }, (_, weekIndex) => (
                <div className="reminder-calendar-week" key={`week-${weekIndex}`} role="row">
                  {cells.slice(weekIndex * 7, weekIndex * 7 + 7).map((date, dayIndex) =>
                    date ? (
                      <div
                        aria-selected={formatDate(date) === value}
                        className="reminder-calendar-cell"
                        key={formatDate(date)}
                        role="gridcell"
                      >
                        <button
                          aria-label={formatDate(date)}
                          className={[
                            "reminder-calendar-day",
                            formatDate(date) === today ? "is-today" : "",
                            formatDate(date) === value ? "is-selected" : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          disabled={formatDate(date) < minDate}
                          id={`${id}-${formatDate(date)}`}
                          onClick={() => selectDate(date)}
                          onKeyDown={(event) => handleDateKeyDown(event, date)}
                          onFocus={() => setActiveDate(date)}
                          type="button"
                        >
                          {date.getDate()}
                        </button>
                      </div>
                    ) : (
                      <div
                        aria-hidden="true"
                        className="reminder-calendar-cell is-empty"
                        key={`empty-${weekIndex}-${dayIndex}`}
                        role="gridcell"
                      />
                    ),
                  )}
                </div>
              ))}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

interface ReminderTimePickerProps {
  disabled?: boolean;
  invalid?: boolean;
  label: string;
  onChange: (value: string) => void;
  value: string;
}

/** 双列 24 小时时间选择器，分钟粒度为 1 分钟。 */
export function ReminderTimePicker({
  disabled = false,
  invalid = false,
  label,
  onChange,
  value,
}: ReminderTimePickerProps) {
  const id = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const parsed = parseTime(value);
  const { hour, minute } = parsed;
  const isOpen = open && !disabled;
  const popoverStyle = usePopoverPosition(isOpen, triggerRef, panelRef, false);
  const close = useCallback((restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);
  useDismiss(isOpen, triggerRef, panelRef, close);

  function selectHour(nextHour: number) {
    onChange(`${pad2(nextHour)}:${pad2(minute)}`);
  }

  function selectMinute(nextMinute: number) {
    onChange(`${pad2(hour)}:${pad2(nextMinute)}`);
  }

  function handleColumnTab(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "Tab") return;
    event.preventDefault();
    close();
    moveFocusFromTrigger(triggerRef.current, event.shiftKey);
  }

  return (
    <>
      <button
        aria-controls={id}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
        aria-label={label}
        aria-invalid={invalid || undefined}
        className="reminder-picker-trigger"
        disabled={disabled}
        onClick={() => {
          if (isOpen) close();
          else setOpen(true);
        }}
        ref={triggerRef}
        type="button"
      >
        <span>{isValidTime(value) ? value : "选择时间"}</span>
        <PlatformIcon name="clock" size={17} />
      </button>
      {isOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            aria-label="选择提醒时间"
            className="reminder-time-popover"
            id={id}
            onKeyDown={(event) => {
              if (event.defaultPrevented) return;
              if (event.key === "Escape") {
                event.preventDefault();
                close(true);
              } else if (event.key === "Tab") {
                event.preventDefault();
                close();
                moveFocusFromTrigger(triggerRef.current, event.shiftKey);
              }
            }}
            ref={panelRef}
            role="dialog"
            style={popoverStyle}
          >
            <div className="reminder-time-columns">
              <TimeColumn
                autoFocus
                label="小时"
                onChange={selectHour}
                onKeyDown={handleColumnTab}
                selected={hour}
                values={HOURS}
              />
              <TimeColumn
                label="分钟"
                onChange={selectMinute}
                onKeyDown={handleColumnTab}
                selected={minute}
                values={MINUTES}
              />
            </div>
            <button className="reminder-time-done" onClick={() => close(true)} type="button">
              完成
            </button>
          </div>,
          document.body,
        )}
    </>
  );
}

interface ReminderTimezoneSelectProps {
  disabled?: boolean;
  invalid?: boolean;
  onChange: (value: string) => void;
  value: string;
}

/** 从浏览器支持的 IANA 时区中选择；保留已有别名以兼容编辑旧提醒。 */
export function ReminderTimezoneSelect({
  disabled = false,
  invalid = false,
  onChange,
  value,
}: ReminderTimezoneSelectProps) {
  const options = getSupportedTimezones();
  if (value && !options.includes(value)) options.unshift(value);

  return (
    <select
      aria-label="时区"
      aria-invalid={invalid || undefined}
      className="reminder-native-select"
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      value={value}
    >
      {options.map((timezone) => (
        <option key={timezone} value={timezone}>
          {timezone}
        </option>
      ))}
    </select>
  );
}

interface TimeColumnProps {
  autoFocus?: boolean;
  label: string;
  onChange: (value: number) => void;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => void;
  selected: number;
  values: number[];
}

function TimeColumn({
  autoFocus = false,
  label,
  onChange,
  onKeyDown,
  selected,
  values,
}: TimeColumnProps) {
  const id = useId();
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoFocus) listRef.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>(`[data-value="${selected}"]`)?.scrollIntoView?.({
      block: "center",
    });
  }, [selected]);

  function focusValue(nextValue: number) {
    const next = Math.max(values[0] ?? 0, Math.min(values[values.length - 1] ?? 0, nextValue));
    onChange(next);
    listRef.current?.querySelector<HTMLElement>(`[data-value="${next}"]`)?.scrollIntoView?.({
      block: "nearest",
    });
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    onKeyDown(event);
    if (event.defaultPrevented) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      focusValue(selected + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      focusValue(selected - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      focusValue(values[0] ?? 0);
    } else if (event.key === "End") {
      event.preventDefault();
      focusValue(values[values.length - 1] ?? 0);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onChange(selected);
    }
  }

  return (
    <div className="reminder-time-column">
      <span>{label}</span>
      <div
        aria-activedescendant={`${id}-${selected}`}
        aria-label={label}
        className="reminder-time-options"
        onKeyDown={handleKeyDown}
        ref={listRef}
        role="listbox"
        tabIndex={0}
      >
        {values.map((option) => (
          <div
            aria-selected={option === selected}
            className={`reminder-time-option${option === selected ? " is-selected" : ""}`}
            data-value={option}
            id={`${id}-${option}`}
            key={option}
            onClick={() => {
              onChange(option);
            }}
            role="option"
          >
            {pad2(option)}
          </div>
        ))}
      </div>
    </div>
  );
}

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];
const HOURS = Array.from({ length: 24 }, (_, index) => index);
const MINUTES = Array.from({ length: 60 }, (_, index) => index);

function usePopoverPosition(
  open: boolean,
  anchorRef: RefObject<HTMLElement | null>,
  panelRef: RefObject<HTMLElement | null>,
  matchAnchorWidth: boolean,
) {
  const [style, setStyle] = useState<CSSProperties>({
    position: "fixed",
    visibility: "hidden",
  });

  useLayoutEffect(() => {
    if (!open) return;
    const anchor = anchorRef.current;
    const panel = panelRef.current;
    if (!anchor || !panel) return;

    const update = () => {
      const bounds = anchor.getBoundingClientRect();
      const panelBounds = panel.getBoundingClientRect();
      const margin = 12;
      const gap = 6;
      const width = matchAnchorWidth
        ? bounds.width
        : Math.min(panelBounds.width, window.innerWidth - margin * 2);
      const height = Math.min(panelBounds.height, window.innerHeight - margin * 2);
      const below = window.innerHeight - bounds.bottom - margin;
      const above = bounds.top - margin;
      const openAbove = below < height + gap && above > below;
      const top = openAbove ? bounds.top - height - gap : bounds.bottom + gap;
      const left = Math.max(margin, Math.min(bounds.left, window.innerWidth - width - margin));

      setStyle({
        left,
        maxHeight: `calc(100vh - ${margin * 2}px)`,
        position: "fixed",
        top: Math.max(margin, Math.min(top, window.innerHeight - height - margin)),
        visibility: "visible",
        width,
      });
    };

    const frame = window.requestAnimationFrame(update);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [anchorRef, matchAnchorWidth, open, panelRef]);

  return style;
}

function useDismiss(
  open: boolean,
  anchorRef: RefObject<HTMLElement | null>,
  panelRef: RefObject<HTMLElement | null>,
  close: (restoreFocus?: boolean) => void,
) {
  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent) {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (anchorRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      close();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [anchorRef, close, open, panelRef]);
}

function moveFocusFromTrigger(trigger: HTMLButtonElement | null, backwards: boolean) {
  const form = trigger?.closest("form");
  if (!form || !trigger) return;
  const controls = Array.from(
    form.querySelectorAll<HTMLElement>(
      'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    ),
  );
  const index = controls.indexOf(trigger);
  const next = controls[index + (backwards ? -1 : 1)];
  if (next) next.focus();
  else trigger.blur();
}

function getSupportedTimezones(): string[] {
  const intl = Intl as typeof Intl & {
    supportedValuesOf?: (key: "timeZone") => string[];
  };
  const supported = intl.supportedValuesOf?.("timeZone") ?? [
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Australia/Sydney",
    "Europe/London",
    "Europe/Paris",
    "America/Los_Angeles",
    "America/New_York",
  ];
  return ["UTC", ...supported.filter((timezone) => timezone !== "UTC")];
}

function getCalendarCells(month: Date): Array<Date | null> {
  const offset = new Date(month.getFullYear(), month.getMonth(), 1).getDay();
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cellCount = Math.ceil((offset + daysInMonth) / 7) * 7;
  return Array.from({ length: cellCount }, (_, index) => {
    const day = index - offset + 1;
    return day > 0 && day <= daysInMonth
      ? new Date(month.getFullYear(), month.getMonth(), day)
      : null;
  });
}

function formatDate(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function formatDateInTimezone(date: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: timezone,
    year: "numeric",
  }).formatToParts(date);
  const values = new Map(parts.map(({ type, value }) => [type, value]));
  return `${values.get("year")}-${values.get("month")}-${values.get("day")}`;
}

function formatMonth(date: Date): string {
  return `${date.getFullYear()}年${pad2(date.getMonth() + 1)}月`;
}

function firstOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addMonths(date: Date, amount: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + amount, 1);
}

function isPreviousMonthDisabled(month: Date, minDate: string): boolean {
  const previousMonthEnd = new Date(month.getFullYear(), month.getMonth(), 0);
  return formatDate(previousMonthEnd) < minDate;
}

function parseDate(value: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const [, yearText, monthText, dayText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day
    ? date
    : null;
}

function parseTime(value: string): { hour: number; minute: number } {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match || !isValidTime(value)) return { hour: 9, minute: 0 };
  return { hour: Number(match[1]), minute: Number(match[2]) };
}

function isValidTime(value: string): boolean {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return false;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
}

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}
