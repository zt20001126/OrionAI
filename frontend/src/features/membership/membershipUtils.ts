import type { MembershipOrderStatus } from "./types";

const DAY_IN_MS = 24 * 60 * 60 * 1000;

export function getRemainingDays(expiresAt: string, now = Date.now()): number {
  const expiry = Date.parse(expiresAt);
  if (!Number.isFinite(expiry)) return 0;
  return Math.max(0, Math.ceil((expiry - now) / DAY_IN_MS));
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatDuration(days: number): string {
  if (!Number.isFinite(days) || days <= 0) return "有效期信息暂不可用";
  return days + " 天";
}

export function getOrderStatusLabel(status: MembershipOrderStatus): string {
  const labels: Record<MembershipOrderStatus, string> = {
    pending: "待支付",
    paid: "已支付",
    failed: "支付失败",
    expired: "已过期",
  };
  return labels[status];
}

export function getOrderStatusClass(status: MembershipOrderStatus): string {
  const classes: Record<MembershipOrderStatus, string> = {
    pending: "pending",
    paid: "paid",
    failed: "failed",
    expired: "expired",
  };
  return classes[status];
}

export function getRecommendedPlanId<T extends { id: string; duration_days: number }>(
  plans: T[],
): string | null {
  if (plans.length !== 3) return null;
  const sorted = [...plans].sort((left, right) => left.duration_days - right.duration_days);
  return sorted[1]?.id ?? null;
}
