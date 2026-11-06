import { useEffect } from "react";

import { PlatformIcon } from "./PlatformIcon";
import type { MarketSkill } from "./skillApi";
import { t } from "../../i18n/localeStore";

interface SkillDetailsDialogProps {
  onClose: () => void;
  skill: MarketSkill;
}

/** 展示技能目录中的描述和状态，并保留键盘及遮罩关闭行为。 */
export function SkillDetailsDialog({ onClose, skill }: SkillDetailsDialogProps) {
  const [imageUnavailable, setImageUnavailable] = useState(false);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }

    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const demoFileByCode: Record<string, string> = {
    general_chat: "agent.gif",
    image_agent: "image_agent.gif",
    resume_assistant: "resume_agent.gif",
    reminder: "reminders.gif",
    memory_training: "memory_training.gif",
    digital_human: "digital_human.gif",
    tourism_insight: "wenxain_agent.gif",
  };
  const demoFile = demoFileByCode[skill.code] ?? `${skill.name}.gif`;
  const demoUrl = `/feature_detail/${encodeURIComponent(demoFile)}`;

  useEffect(() => setImageUnavailable(false), [demoUrl]);

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
        <button aria-label={t("关闭技能详情")} className="dialog-close" onClick={onClose} type="button">
          <PlatformIcon name="close" size={19} />
        </button>
        <div className="skill-card__icon">
          <PlatformIcon name={skill.type === "agent" ? "knowledge" : "tools"} size={26} />
        </div>
        <h2 id="skill-detail-title">{skill.name}</h2>
        <p className="skill-detail-dialog__description">{skill.description || t("暂无技能说明。")}</p>
        <div className="skill-detail-dialog__demo">
          {imageUnavailable ? (
            <div className="skill-detail-dialog__placeholder" role="status">
              {t("暂无功能演示")}
            </div>
          ) : (
            <>
              <span className="skill-detail-dialog__gif-label" aria-hidden="true">GIF</span>
              <img
                alt={t("{name} 功能演示", { name: skill.name })}
                onError={() => setImageUnavailable(true)}
                src={demoUrl}
              />
            </>
          )}
        </div>
      </section>
    </div>
  );
}
