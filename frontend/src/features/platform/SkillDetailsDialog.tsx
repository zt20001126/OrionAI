import { useEffect } from "react";

import { PlatformIcon } from "./PlatformIcon";
import type { DemoSkill } from "./platformData";

interface SkillDetailsDialogProps {
  onClose: () => void;
  skill: DemoSkill;
}

export function SkillDetailsDialog({ onClose, skill }: SkillDetailsDialogProps) {
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      className="dialog-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        aria-labelledby="skill-detail-title"
        aria-modal="true"
        className="skill-detail-dialog"
        role="dialog"
      >
        <button aria-label="关闭技能详情" className="dialog-close" onClick={onClose} type="button">
          <PlatformIcon name="close" size={19} />
        </button>
        <div className={`skill-card__icon skill-card__icon--${skill.icon}`}>
          <PlatformIcon name={skill.icon} size={26} />
        </div>
        <p className="skill-detail-dialog__category">{skill.category} · 演示技能</p>
        <h2 id="skill-detail-title">{skill.name}</h2>
        <p className="skill-detail-dialog__description">{skill.description}</p>
        <div className="skill-detail-dialog__note">
          <span>技能简介</span>
          <p>{skill.details}</p>
        </div>
        <div className="skill-detail-dialog__footer">
          <span>仅用于界面演示，暂不支持执行</span>
          <button className="button button--primary" onClick={onClose} type="button">
            知道了
          </button>
        </div>
      </section>
    </div>
  );
}
