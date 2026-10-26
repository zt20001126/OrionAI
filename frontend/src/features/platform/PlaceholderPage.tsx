import { PlatformIcon, type PlatformIconName } from "./PlatformIcon";
import { platformPaths, type PlatformPath } from "./platformData";

type PlaceholderPath = Exclude<PlatformPath, "/market">;

const pageContent: Record<PlaceholderPath, { title: string; icon: PlatformIconName }> = {
  "/agents": { title: "我的智能体", icon: "agents" },
  "/sessions": { title: "会话记录", icon: "sessions" },
  "/knowledge": { title: "知识库", icon: "knowledge" },
  "/tools": { title: "工具管理", icon: "tools" },
  "/workspace": { title: "个人空间", icon: "workspace" },
  "/settings": { title: "个人设置", icon: "settings" },
};

interface PlaceholderPageProps {
  onNavigate: (path: PlatformPath) => void;
  pathname: PlaceholderPath;
}

export function PlaceholderPage({ onNavigate, pathname }: PlaceholderPageProps) {
  const content = pageContent[pathname];

  return (
    <section aria-labelledby="placeholder-title" className="placeholder-page">
      <div className="placeholder-page__icon">
        <PlatformIcon name={content.icon} size={28} />
      </div>
      <p className="section-eyebrow">ORIONAI WORKSPACE</p>
      <h1 id="placeholder-title">{content.title}</h1>
      <p>该页面正在建设中，敬请期待。</p>
      <button
        className="button button--outline"
        onClick={() => onNavigate(platformPaths.market)}
        type="button"
      >
        <PlatformIcon name="arrow" size={16} />
        返回技能市场
      </button>
    </section>
  );
}
