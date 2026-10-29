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
  chat: "/chat",
  login: "/login",
} as const;

export type PlatformPath = Exclude<
  (typeof platformPaths)[keyof typeof platformPaths],
  "/login" | "/chat"
>;
export type ConversationPath = typeof platformPaths.chat | `${typeof platformPaths.chat}/${string}`;
export type PlatformRoute = PlatformPath | ConversationPath;

export function isPlatformPath(pathname: string): pathname is PlatformRoute {
  if (pathname === platformPaths.chat) return true;

  if (pathname.startsWith(`${platformPaths.chat}/`)) {
    return /^\/chat\/\d+$/.test(pathname);
  }

  return Object.values(platformPaths).some(
    (path) => path !== platformPaths.login && path !== platformPaths.chat && path === pathname,
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
  return localPart || "个人用户";
}
