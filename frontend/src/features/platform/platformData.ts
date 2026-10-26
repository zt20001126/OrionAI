export const platformPaths = {
  market: "/market",
  agents: "/agents",
  sessions: "/sessions",
  knowledge: "/knowledge",
  tools: "/tools",
  workspace: "/workspace",
  settings: "/settings",
  login: "/login",
} as const;

export type PlatformPath = Exclude<(typeof platformPaths)[keyof typeof platformPaths], "/login">;

export function isPlatformPath(pathname: string): pathname is PlatformPath {
  return Object.values(platformPaths).some(
    (path) => path !== platformPaths.login && path === pathname,
  );
}

export const navigationItems = [
  { path: platformPaths.market, label: "技能市场", icon: "market" },
  { path: platformPaths.agents, label: "我的智能体", icon: "agents" },
  { path: platformPaths.sessions, label: "会话记录", icon: "sessions" },
  { path: platformPaths.knowledge, label: "知识库", icon: "knowledge" },
  { path: platformPaths.tools, label: "工具管理", icon: "tools" },
] as const;

export const skillCategories = [
  "全部",
  "知识问答",
  "内容生成",
  "数据处理",
  "开发辅助",
  "效率工具",
] as const;

export type SkillCategory = (typeof skillCategories)[number];
export type SkillIconName = "knowledge" | "tools" | "document" | "data";

export interface DemoSkill {
  id: string;
  name: string;
  description: string;
  category: Exclude<SkillCategory, "全部">;
  icon: SkillIconName;
  keywords: string[];
  details: string;
}

export const demoSkills: DemoSkill[] = [
  {
    id: "rag-knowledge-qa",
    name: "RAG 知识问答",
    description: "基于知识库的检索增强问答。",
    category: "知识问答",
    icon: "knowledge",
    keywords: ["RAG", "知识库", "检索", "问答", "企业知识"],
    details: "连接知识内容与生成式问答，让智能体能够结合相关资料回答问题。",
  },
  {
    id: "tool-calling",
    name: "工具调用",
    description: "让 AI 使用外部工具完成任务。",
    category: "效率工具",
    icon: "tools",
    keywords: ["工具", "调用", "自动化", "效率"],
    details: "为智能体提供调用外部工具的能力，帮助它完成多步骤任务。",
  },
  {
    id: "document-analysis",
    name: "文档分析",
    description: "解析、总结与提取文档内容。",
    category: "数据处理",
    icon: "document",
    keywords: ["文档", "分析", "总结", "提取", "PDF"],
    details: "整理文档中的关键信息，支持摘要、内容提取和结构化理解。",
  },
  {
    id: "data-analysis",
    name: "数据分析",
    description: "对结构化数据进行分析与洞察。",
    category: "数据处理",
    icon: "data",
    keywords: ["数据", "分析", "洞察", "表格", "结构化"],
    details: "帮助智能体理解结构化数据，并生成清晰的分析摘要与洞察。",
  },
];

export function getDisplayName(account: string): string {
  const localPart = account.split("@")[0]?.trim();
  return localPart || "个人用户";
}
