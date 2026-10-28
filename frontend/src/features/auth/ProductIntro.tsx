import { PlatformIcon, type PlatformIconName } from "../platform/PlatformIcon";
import { AuthWorkspacePreview } from "./AuthWorkspacePreview";

const capabilities: {
  title: string;
  description: string;
  icon: PlatformIconName;
}[] = [
  {
    title: "丰富的技能市场",
    description: "发现不同领域的 AI 能力",
    icon: "market",
  },
  {
    title: "专属智能体",
    description: "选择适合任务的智能助手",
    icon: "assistant",
  },
  {
    title: "实用 AI 工具",
    description: "高效处理各类日常任务",
    icon: "tools",
  },
  {
    title: "持续扩展",
    description: "更多应用场景不断加入",
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
          <span className="product-kicker">一站式 AI 智能应用平台</span>
          <h1 id="product-title">你的 AI 全能工作空间</h1>
          <p>汇集多种 AI 智能体与实用工具，让不同问题都能找到合适的解决方式。</p>
        </div>

        <ul aria-label="OrionAI 核心能力" className="product-capabilities">
          {capabilities.map((capability) => (
            <li className="product-capability" key={capability.title}>
              <span className="product-capability-icon">
                <PlatformIcon name={capability.icon} size={19} />
              </span>
              <span className="product-capability-copy">
                <strong>{capability.title}</strong>
                <span>{capability.description}</span>
              </span>
            </li>
          ))}
        </ul>

        <AuthWorkspacePreview />
      </div>
    </aside>
  );
}

export function BrandMark() {
  return <img className="brand-mark" src="/logo/orionai-logo-512.png" alt="" aria-hidden="true" />;
}
