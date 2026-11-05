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
  digitalHuman: "/digital-human",
  tourismInsight: "/tourism-insight",
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
  "/login" | "/chat" | "/membership/checkout" | "/tourism-insight"
>;
export type ConversationPath = typeof platformPaths.chat | `${typeof platformPaths.chat}/${string}`;
export type DigitalHumanConversationPath =
  typeof platformPaths.digitalHuman | `${typeof platformPaths.digitalHuman}/${string}`;
export type TourismInsightPath = `${typeof platformPaths.tourismInsight}/${string}`;
export type MembershipCheckoutPath = string & { readonly __membershipCheckoutPath: unique symbol };
export type MembershipOrderDetailPath = string & {
  readonly __membershipOrderDetailPath: unique symbol;
};
export type PlatformRoute =
  | PlatformPath
  | ConversationPath
  | DigitalHumanConversationPath
  | TourismInsightPath
  | MembershipCheckoutPath
  | MembershipOrderDetailPath;

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

  if (pathname === platformPaths.digitalHuman) return true;
  if (pathname.startsWith(`${platformPaths.digitalHuman}/`)) {
    return /^\/digital-human\/\d+$/.test(pathname);
  }

  if (pathname.startsWith(`${platformPaths.tourismInsight}/`)) {
    return /^\/tourism-insight\/\d+$/.test(pathname);
  }

  if (isMembershipCheckoutPath(pathname) || isMembershipOrderDetailPath(pathname)) return true;

  return Object.values(platformPaths).some(
    (path) =>
      path !== platformPaths.login &&
      path !== platformPaths.chat &&
      path !== platformPaths.tourismInsight &&
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

export function getDigitalHumanConversationId(pathname: PlatformRoute): string | null {
  if (!pathname.startsWith(`${platformPaths.digitalHuman}/`)) return null;
  return pathname.slice(`${platformPaths.digitalHuman}/`.length);
}

export function isDigitalHumanPath(
  pathname: PlatformRoute,
): pathname is DigitalHumanConversationPath {
  return (
    pathname === platformPaths.digitalHuman || pathname.startsWith(`${platformPaths.digitalHuman}/`)
  );
}

export function getTourismInsightConversationId(pathname: PlatformRoute): string | null {
  if (!pathname.startsWith(`${platformPaths.tourismInsight}/`)) return null;
  return pathname.slice(`${platformPaths.tourismInsight}/`.length);
}

export function isTourismInsightPath(pathname: PlatformRoute): pathname is TourismInsightPath {
  return /^\/tourism-insight\/\d+$/.test(pathname);
}

export const navigationItems = [
  { path: platformPaths.market, label: "技能市场", icon: "market" },
  { path: platformPaths.mySkills, label: "我的技能", icon: "agents" },
  { path: platformPaths.digitalHuman, label: "我的数字人", icon: "assistant" },
  { path: platformPaths.sessions, label: "会话记录", icon: "sessions" },
] as const;

export const skillCategories = ["全部", "智能体", "工具"] as const;

export type SkillCategory = (typeof skillCategories)[number];

export function getDisplayName(account: string): string {
  const localPart = account.split("@")[0]?.trim();
  return localPart || t("个人用户");
}
