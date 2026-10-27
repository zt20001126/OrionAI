import { PlatformIcon, type PlatformIconName } from "./PlatformIcon";
import { platformPaths, type PlatformPath, type PlatformRoute } from "./platformData";

type PlaceholderPath = Exclude<
  PlatformPath,
  "/market" | "/agents" | "/sessions" | "/settings"
>;

const pageContent: Record<PlaceholderPath, { title: string; icon: PlatformIconName }> = {
  "/knowledge": { title: "知识库", icon: "knowledge" },
  "/tools": { title: "工具管理", icon: "tools" },
  "/workspace": { title: "个人空间", icon: "workspace" },
};

interface PlaceholderPageProps {
  onNavigate: (path: PlatformRoute) => void;
  pathname: PlaceholderPath;
}

export function PlaceholderPage({ onNavigate, pathname }: PlaceholderPageProps) {
  const content = pageContent[pathname];

  return (
    <section aria-labelledby="placeholder-title" className="placeholder-page">
      <span aria-hidden="true" className="placeholder-page__icon">
        <PlatformIcon name={content.icon} size={28} />
      </span>
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
