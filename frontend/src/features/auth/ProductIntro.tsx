import { PlatformIcon, type PlatformIconName } from "../platform/PlatformIcon";
import { AuthSkillsPreview } from "./AuthSkillsPreview";
import { t } from "../../i18n/localeStore";

const capabilities: {
  title: string;
  description: string;
  icon: PlatformIconName;
}[] = [
  {
    title: "丰富的智能体",
    description: "多种专业 AI 助手",
    icon: "market",
  },
  {
    title: "实用工具",
    description: "轻松处理日常任务",
    icon: "tools",
  },
  {
    title: "智能交互",
    description: "自然流畅的 AI 对话",
    icon: "sessions",
  },
  {
    title: "持续更新",
    description: "探索更多 AI 应用",
    icon: "agents",
  },
];

export function ProductIntro() {
  return (
    <aside aria-labelledby="product-title" className="product-panel">
      <div className="product-content">
        <div className="brand-lockup">
          <BrandMark />
          <span>OrionAI</span>
        </div>

        <div className="product-copy">
          <span className="product-kicker">{t("一站式 AI 智能体与工具平台")}</span>
          <h1 id="product-title">{t("探索 AI 的更多可能")}</h1>
          <p>{t("从智能对话到专业任务处理，发现适合不同场景的 AI 智能体与工具。")}</p>
        </div>

        <ul aria-label={t("OrionAI 核心能力")} className="product-capabilities">
          {capabilities.map((capability) => (
            <li className="product-capability" key={capability.title}>
              <span className="product-capability-icon">
                <PlatformIcon name={capability.icon} size={19} />
              </span>
              <span className="product-capability-copy">
                <strong>{t(capability.title)}</strong>
                <span>{t(capability.description)}</span>
              </span>
            </li>
          ))}
        </ul>

        <AuthSkillsPreview />
      </div>
    </aside>
  );
}

export function BrandMark() {
  return <img className="brand-mark" src="/logo/orionai-logo-512.png" alt="" aria-hidden="true" />;
}
