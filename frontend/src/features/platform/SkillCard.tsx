import type { ReactNode } from "react";

import { PlatformIcon } from "./PlatformIcon";
import type { MarketSkill } from "./skillApi";

interface SkillCardProps {
  actions: ReactNode;
  onView: (skill: MarketSkill) => void;
  skill: MarketSkill;
}

/** 展示数据库中的单项技能，并将详情查看交由页面处理。 */
export function SkillCard({ actions, onView, skill }: SkillCardProps) {
  const category = skill.type === "agent" ? "智能体" : "工具";
  const icon = skill.type === "agent" ? "knowledge" : "tools";
  const status = skill.status === "disabled" ? "已停用" : skill.is_added ? "已添加" : "可添加";
  const statusClass =
    skill.status === "disabled" ? "disabled" : skill.is_added ? "added" : "available";

  return (
    <article className="skill-card">
      <div className="skill-card__header">
        <div className={`skill-card__icon skill-card__icon--${icon}`}>
          <PlatformIcon name={icon} size={25} />
        </div>
        <span className={`skill-card__status skill-card__status--${statusClass}`}>{status}</span>
      </div>
      <div className="skill-card__content">
        <h3>{skill.name}</h3>
        <span className="skill-card__type">{category}</span>
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
