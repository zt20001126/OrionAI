import { t } from "../../i18n/localeStore";

export const platformPaths = {
  market: "/market",
  mySkills: "/agents",
  sessions: "/sessions",
  resume: "/resume",
  knowledge: "/knowledge",
  tools: "/tools",
  reminders: "/reminders",
  reminderCreate: "/reminders/new",
  memoryTraining: "/memory-training",
  settings: "/settings",
  securitySettings: "/settings/security",
  feedbackSettings: "/settings/feedback",
  membership: "/membership",
  membershipCheckout: "/membership/checkout",
  membershipOrders: "/membership/orders",
  chat: "/chat",
  login: "/login",
} as const;

export type PlatformPath = Exclude<
  (typeof platformPaths)[keyof typeof platformPaths],
  "/login" | "/chat" | "/membership/checkout"
>;
export type ConversationPath = typeof platformPaths.chat | `${typeof platformPaths.chat}/${string}`;
export type MembershipCheckoutPath = string & { readonly __membershipCheckoutPath: unique symbol };
export type MembershipOrderDetailPath = string & {
  readonly __membershipOrderDetailPath: unique symbol;
};
export type PlatformRoute =
  PlatformPath | ConversationPath | MembershipCheckoutPath | MembershipOrderDetailPath;

export function isSettingsPath(pathname: string): boolean {
  return (
    pathname === platformPaths.settings ||
    pathname === platformPaths.securitySettings ||
    pathname === platformPaths.feedbackSettings
  );
}

export function createMembershipCheckoutPath(
  planId: string,
  orderId?: string,
): MembershipCheckoutPath {
  const checkoutPath = `${platformPaths.membershipCheckout}/${encodeURIComponent(planId)}`;
  return (
    orderId ? `${checkoutPath}/order/${encodeURIComponent(orderId)}` : checkoutPath
  ) as MembershipCheckoutPath;
}

export function createMembershipOrderDetailPath(orderId: string): MembershipOrderDetailPath {
  return `${platformPaths.membershipOrders}/${encodeURIComponent(orderId)}` as MembershipOrderDetailPath;
}

export function getMembershipCheckoutPlanId(pathname: string): string | null {
  const match = pathname.match(/^\/membership\/checkout\/([0-9]+)(?:\/order\/[0-9]+)?$/);
  return match?.[1] ?? null;
}

export function getMembershipCheckoutOrderId(pathname: string): string | null {
  const match = pathname.match(/^\/membership\/checkout\/[0-9]+\/order\/([0-9]+)$/);
  return match?.[1] ?? null;
}

export function getMembershipOrderId(pathname: string): string | null {
  const match = pathname.match(/^\/membership\/orders\/([0-9]+)$/);
  return match?.[1] ?? null;
}

export function isMembershipCheckoutPath(pathname: string): pathname is MembershipCheckoutPath {
  return getMembershipCheckoutPlanId(pathname) !== null;
}

export function isMembershipOrderDetailPath(
  pathname: string,
): pathname is MembershipOrderDetailPath {
  return getMembershipOrderId(pathname) !== null;
}

export function isPlatformPath(pathname: string): pathname is PlatformRoute {
  if (pathname === platformPaths.chat) return true;

  if (pathname.startsWith(`${platformPaths.chat}/`)) {
    return /^\/chat\/\d+$/.test(pathname);
  }

  if (isMembershipCheckoutPath(pathname) || isMembershipOrderDetailPath(pathname)) return true;

  return Object.values(platformPaths).some(
    (path) =>
      path !== platformPaths.login &&
      path !== platformPaths.chat &&
      path !== platformPaths.membershipCheckout &&
      path === pathname,
  );
}

export function getConversationId(pathname: PlatformRoute): string | null {
  if (!pathname.startsWith(`${platformPaths.chat}/`)) return null;
  return pathname.slice(`${platformPaths.chat}/`.length);
}

export function isConversationPath(pathname: PlatformRoute): pathname is ConversationPath {
  return pathname === platformPaths.chat || pathname.startsWith(`${platformPaths.chat}/`);
}

export const navigationItems = [
  { path: platformPaths.market, label: "技能市场", icon: "market" },
  { path: platformPaths.mySkills, label: "我的技能", icon: "agents" },
  { path: platformPaths.sessions, label: "会话记录", icon: "sessions" },
  { path: platformPaths.knowledge, label: "知识库", icon: "knowledge" },
  { path: platformPaths.tools, label: "工具管理", icon: "tools" },
] as const;

export const skillCategories = ["全部", "智能体", "工具"] as const;

export type SkillCategory = (typeof skillCategories)[number];

export function getDisplayName(account: string): string {
  const localPart = account.split("@")[0]?.trim();
  return localPart || t("个人用户");
}
