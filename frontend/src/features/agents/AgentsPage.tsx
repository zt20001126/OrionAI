import { PlatformIcon } from "../platform/PlatformIcon";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import "./agents.css";

interface AgentsPageProps {
  onNavigate: (path: PlatformRoute) => void;
}

export function AgentsPage({ onNavigate }: AgentsPageProps) {
  return (
    <section aria-labelledby="agents-title" className="agents-page">
      <header className="agents-page__header">
        <div>
          <h1 id="agents-title">我的智能体</h1>
          <p>管理和使用你的 AI 智能体</p>
        </div>
        <button
          aria-label="添加智能体，暂未开放"
          className="button button--secondary agents-page__add"
          disabled
          type="button"
        >
          <span aria-hidden="true">+</span>
          添加
          <span className="agents-page__unavailable">暂未开放</span>
        </button>
      </header>

      <div className="agents-page__grid">
        <button className="agent-card" onClick={() => onNavigate(platformPaths.chat)} type="button">
          <span aria-hidden="true" className="agent-card__icon">
            <PlatformIcon name="assistant" size={22} />
          </span>
          <span className="agent-card__title">通用对话助手</span>
          <span className="agent-card__description">支持日常问答和多轮对话</span>
          <span className="agent-card__footer">
            <span className="agent-card__available">可使用</span>
            <PlatformIcon name="arrow" size={17} />
          </span>
        </button>

        <button className="agent-card agent-card--unavailable" disabled type="button">
          <span aria-hidden="true" className="agent-card__add-icon">
            +
          </span>
          <span className="agent-card__add-title">添加更多智能体</span>
          <span className="agent-card__unavailable-label">暂未开放</span>
        </button>
      </div>
    </section>
  );
}
