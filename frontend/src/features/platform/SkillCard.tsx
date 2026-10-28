import type { ReactNode } from "react";

import { PlatformIcon, type PlatformIconName } from "./PlatformIcon";
import type { MarketSkill } from "./skillApi";

interface SkillCardProps {
  actions: ReactNode;
  onView: (skill: MarketSkill) => void;
  skill: MarketSkill;
}

interface SkillVisual {
  icon: PlatformIconName;
  tone: "blue" | "sky" | "violet";
}

const skillVisualRules: {
  keywords: string[];
  visual: SkillVisual;
}[] = [
  {
    keywords: ["image", "photo", "picture", "vision", "图片", "图像"],
    visual: { icon: "camera", tone: "sky" },
  },
  {
    keywords: ["resume", "document", "writing", "简历", "文档"],
    visual: { icon: "document", tone: "blue" },
  },
  {
    keywords: ["chat", "conversation", "dialog", "对话"],
    visual: { icon: "assistant", tone: "violet" },
  },
  {
    keywords: ["data", "analytics", "chart", "数据", "分析"],
    visual: { icon: "data", tone: "sky" },
  },
  {
    keywords: ["knowledge", "research", "search", "知识", "检索"],
    visual: { icon: "knowledge", tone: "violet" },
  },
  { keywords: ["automation", "自动化"], visual: { icon: "tools", tone: "blue" } },
];

const fallbackVisuals: Record<MarketSkill["type"], SkillVisual[]> = {
  agent: [
    { icon: "assistant", tone: "violet" },
    { icon: "knowledge", tone: "blue" },
    { icon: "document", tone: "sky" },
    { icon: "data", tone: "violet" },
  ],
  tool: [
    { icon: "tools", tone: "blue" },
    { icon: "data", tone: "sky" },
    { icon: "camera", tone: "violet" },
    { icon: "search", tone: "blue" },
  ],
};

function getSkillVisual(skill: MarketSkill): SkillVisual {
  const searchableName = `${skill.code} ${skill.name}`.toLocaleLowerCase();
  const matchedRule = skillVisualRules.find(({ keywords }) =>
    keywords.some((keyword) => searchableName.includes(keyword)),
  );

  if (matchedRule) return matchedRule.visual;

  const stableIndex = Array.from(skill.code).reduce(
    (hash, character) => (hash * 31 + character.charCodeAt(0)) >>> 0,
    0,
  );
  const options = fallbackVisuals[skill.type];
  return options[stableIndex % options.length];
}

/** 展示数据库中的单项技能，并将详情查看交由页面处理。 */
export function SkillCard({ actions, onView, skill }: SkillCardProps) {
  const category = skill.type === "agent" ? "智能体" : "工具";
  const visual = getSkillVisual(skill);
  const status = skill.status === "disabled" ? "已停用" : skill.is_added ? "已添加" : "可添加";
  const statusClass =
    skill.status === "disabled" ? "disabled" : skill.is_added ? "added" : "available";

  return (
    <article className="skill-card">
      <div className="skill-card__header">
        <div className="skill-card__identity">
          <div className={`skill-card__icon skill-card__icon--${visual.tone}`}>
            <PlatformIcon name={visual.icon} size={22} />
          </div>
          <div className="skill-card__heading">
            <h3>{skill.name}</h3>
            <span className="skill-card__type">{category}</span>
          </div>
        </div>
        <span className={`skill-card__status skill-card__status--${statusClass}`}>{status}</span>
      </div>
      <div className="skill-card__content">
        <p>{skill.description}</p>
      </div>
      <div className="skill-card__actions">
        <button
          aria-label={`查看 ${skill.name} 详情`}
          className="skill-card__action"
          onClick={() => onView(skill)}
          type="button"
        >
          查看详情
          <PlatformIcon name="arrow" size={16} />
        </button>
        <div className="skill-card__action-group">{actions}</div>
      </div>
    </article>
  );
}
