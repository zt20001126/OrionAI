import { PlatformIcon, type PlatformIconName } from "../platform/PlatformIcon";
import { t } from "../../i18n/localeStore";

const skills: { title: string; description: string; icon: PlatformIconName; tone: string }[] = [
  {
    title: "简历助手",
    description: "智能优化简历",
    icon: "document",
    tone: "resume",
  },
  {
    title: "提醒助手",
    description: "管理日常提醒",
    icon: "bell",
    tone: "reminder",
  },
  {
    title: "记忆训练",
    description: "观察与记忆练习",
    icon: "knowledge",
    tone: "memory",
  },
  {
    title: "Orion 助手",
    description: "与 AI 数字人语音交流",
    icon: "assistant",
    tone: "digital-human",
  },
];

export function AuthSkillsPreview() {
  return (
    <section aria-label={t("OrionAI 技能市场预览")} className="auth-skills-preview">
      <div className="preview-topbar">
        <span className="preview-window-dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="preview-topbar-label">{t("探索技能市场")}</span>
        <span aria-hidden="true" />
      </div>

      <div className="preview-skill-grid">
        {skills.map((skill) => (
          <article className="preview-skill-card" key={skill.title}>
            <span className={`preview-skill-icon is-${skill.tone}`}>
              <PlatformIcon name={skill.icon} size={17} />
            </span>
            <span className="preview-skill-copy">
              <strong>{t(skill.title)}</strong>
              <span>{t(skill.description)}</span>
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}
