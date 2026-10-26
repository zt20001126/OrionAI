import { PlatformIcon } from "./PlatformIcon";
import type { DemoSkill } from "./platformData";

interface SkillCardProps {
  onView: (skill: DemoSkill) => void;
  skill: DemoSkill;
}

export function SkillCard({ onView, skill }: SkillCardProps) {
  return (
    <article className="skill-card">
      <div className={`skill-card__icon skill-card__icon--${skill.icon}`}>
        <PlatformIcon name={skill.icon} size={25} />
      </div>
      <span className="skill-card__category">{skill.category}</span>
      <h3>{skill.name}</h3>
      <p>{skill.description}</p>
      <button
        aria-label={`查看 ${skill.name} 详情`}
        className="skill-card__action"
        onClick={() => onView(skill)}
        type="button"
      >
        查看
        <PlatformIcon name="arrow" size={16} />
      </button>
    </article>
  );
}
