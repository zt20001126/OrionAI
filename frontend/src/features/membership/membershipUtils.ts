import type { MembershipOrderStatus, MembershipOrderType } from "./types";
import { getLocaleTag, t } from "../../i18n/localeStore";

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
  return new Intl.DateTimeFormat(getLocaleTag(), { dateStyle: "medium" }).format(date);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(getLocaleTag(), {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatDuration(days: number): string {
  if (!Number.isFinite(days) || days <= 0) return t("有效期信息暂不可用");
  return t("{days} 天", { days });
}

export function getOrderStatusLabel(
  status: MembershipOrderStatus,
  orderType: MembershipOrderType = "purchase",
): string {
  if (orderType === "manual_grant" && status === "paid") return t("已赠送");

  const labels: Record<MembershipOrderStatus, string> = {
    pending: "待支付",
    paid: "已支付",
    failed: "支付失败",
    expired: "已过期",
  };
  return t(labels[status]);
}

export function getOrderTypeLabel(orderType: MembershipOrderType): string {
  return t(orderType === "manual_grant" ? "管理员赠送" : "会员购买");
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
