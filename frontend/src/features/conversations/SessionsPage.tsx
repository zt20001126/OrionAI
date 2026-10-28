import { ConversationHistory } from "./ConversationHistory";
import "./conversations.css";

import { platformPaths, type PlatformRoute } from "../platform/platformData";

interface SessionsPageProps {
  onNavigate: (path: PlatformRoute) => void;
}

export function SessionsPage({ onNavigate }: SessionsPageProps) {
  return (
    <section aria-labelledby="sessions-title" className="sessions-page">
      <header className="sessions-page__header">
        <div>
          <h1 id="sessions-title">会话记录</h1>
          <p>查看并继续你与对话助手的历史对话。</p>
        </div>
        <button
          className="button button--primary"
          onClick={() => onNavigate(platformPaths.chat)}
          type="button"
        >
          开始新对话
        </button>
      </header>
      <ConversationHistory
        onSelect={(conversationId) => onNavigate(`${platformPaths.chat}/${conversationId}`)}
        variant="page"
      />
    </section>
  );
}
