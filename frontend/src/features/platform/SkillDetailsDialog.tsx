import { useEffect } from "react";

import { PlatformIcon } from "./PlatformIcon";
import type { MarketSkill } from "./skillApi";

interface SkillDetailsDialogProps {
  onClose: () => void;
  skill: MarketSkill;
}

/** 展示技能目录中的描述和状态，并保留键盘及遮罩关闭行为。 */
export function SkillDetailsDialog({ onClose, skill }: SkillDetailsDialogProps) {
  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const category = skill.type === "agent" ? "智能体" : "工具";
  const status = skill.status === "disabled" ? "已停用" : "已发布";

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
        <div className="skill-card__icon">
          <PlatformIcon name={skill.type === "agent" ? "knowledge" : "tools"} size={26} />
        </div>
        <p className="skill-detail-dialog__category">
          {category} · {status}
        </p>
        <h2 id="skill-detail-title">{skill.name}</h2>
        <p className="skill-detail-dialog__description">{skill.description || "暂无技能说明。"}</p>
        <div className="skill-detail-dialog__note">
          <span>技能代码</span>
          <p>{skill.code}</p>
        </div>
        <div className="skill-detail-dialog__footer">
          <span>
            {skill.status === "disabled" ? "该技能已停用，暂不可添加。" : "技能详情来自技能目录。"}
          </span>
          <button className="button button--primary" onClick={onClose} type="button">
            知道了
          </button>
        </div>
      </section>
    </div>
  );
}
