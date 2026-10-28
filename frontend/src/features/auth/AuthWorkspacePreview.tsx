import { PlatformIcon, type PlatformIconName } from "../platform/PlatformIcon";

const navigation: { label: string; icon: PlatformIconName; active?: boolean }[] = [
  { label: "技能市场", icon: "market", active: true },
  { label: "我的技能", icon: "agents" },
  { label: "智能对话", icon: "sessions" },
  { label: "任务中心", icon: "clock" },
];

const skills: {
  title: string;
  category: string;
  description: string;
  icon: PlatformIconName;
  tone: string;
}[] = [
  {
    title: "简历助手",
    category: "效率工具",
    description: "优化简历内容与表达",
    icon: "document",
    tone: "resume",
  },
  {
    title: "文献助手",
    category: "研究分析",
    description: "快速整理研究资料",
    icon: "knowledge",
    tone: "research",
  },
  {
    title: "图片处理",
    category: "创意工具",
    description: "轻松完成图片编辑",
    icon: "camera",
    tone: "image",
  },
  {
    title: "数据分析",
    category: "数据工具",
    description: "从数据中发现重点",
    icon: "data",
    tone: "data",
  },
];

export function AuthWorkspacePreview() {
  return (
    <section aria-label="OrionAI 工作空间界面预览" className="auth-workspace-preview">
      <div className="preview-topbar">
        <span className="preview-window-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="preview-topbar-label">OrionAI 工作空间</span>
        <span className="preview-avatar" aria-hidden="true">
          O
        </span>
      </div>

      <div className="preview-body">
        <nav aria-label="预览菜单" className="preview-sidebar">
          {navigation.map((item) => (
            <span className={`preview-nav-item${item.active ? " is-active" : ""}`} key={item.label}>
              <PlatformIcon name={item.icon} size={14} />
              {item.label}
            </span>
          ))}
        </nav>

        <div className="preview-main">
          <div className="preview-heading">
            <div>
              <span className="preview-overline">探索 AI 能力</span>
              <h2>技能市场</h2>
            </div>
            <span className="preview-search">
              <PlatformIcon name="search" size={13} /> 搜索技能
            </span>
          </div>
          <div className="preview-skill-grid">
            {skills.map((skill) => (
              <article className="preview-skill-card" key={skill.title}>
                <div className={`preview-skill-icon is-${skill.tone}`}>
                  <PlatformIcon name={skill.icon} size={16} />
                </div>
                <div className="preview-skill-copy">
                  <span>{skill.category}</span>
                  <h3>{skill.title}</h3>
                  <p>{skill.description}</p>
                </div>
                <span className="preview-skill-arrow" aria-hidden="true">
                  ↗
                </span>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
