import { useEffect, useState } from "react";

import {
  getConversationErrorMessage,
  listConversations,
  type ConversationSummary,
} from "./conversationApi";

interface ConversationHistoryProps {
  disabled?: boolean;
  onSelect: (conversationId: string, title: string) => void;
  skillCode?: string;
  selectedId?: string | null;
  variant: "sidebar" | "page" | "embedded";
}

function getConversationLabel(conversation: ConversationSummary): string {
  if (conversation.title?.trim()) return conversation.title;

  const createdAt = new Date(conversation.created_at);
  const dateLabel = Number.isNaN(createdAt.getTime())
    ? ""
    : new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(createdAt);
  return dateLabel ? `未命名会话 · ${dateLabel}` : "未命名会话";
}

export function ConversationHistory({
  disabled = false,
  onSelect,
  skillCode,
  selectedId = null,
  variant,
}: ConversationHistoryProps) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let isActive = true;

    void loadConversationBatch(0, skillCode)
      .then((batch) => {
        if (!isActive) return;
        setConversations(batch.items);
        setOffset(batch.offset);
        setHasMore(batch.hasMore);
        setError(null);
      })
      .catch((requestError: unknown) => {
        if (isActive) setError(getConversationErrorMessage(requestError));
      })
      .finally(() => {
        if (isActive) setIsLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, [retryKey, skillCode]);

  async function loadMore() {
    setIsLoadingMore(true);
    setError(null);
    try {
      const batch = await loadConversationBatch(offset, skillCode);
      setConversations((current) => [...current, ...batch.items]);
      setOffset(batch.offset);
      setHasMore(batch.hasMore);
    } catch (requestError) {
      setError(getConversationErrorMessage(requestError));
    } finally {
      setIsLoadingMore(false);
    }
  }

  return (
    <section
      aria-labelledby={`conversation-history-title-${variant}`}
      className={`conversation-history conversation-history--${variant}`}
    >
      <div className="conversation-history__heading">
        <h2 id={`conversation-history-title-${variant}`}>
          {variant === "sidebar" ? "历史会话" : "所有会话"}
        </h2>
      </div>

      {isLoading && (
        <p className="conversation-history__status" role="status">
          正在加载会话…
        </p>
      )}

      {!isLoading && error && conversations.length === 0 && (
        <div className="conversation-history__empty">
          <p role="alert">{error}</p>
          <button
            className="button button--outline"
            onClick={() => {
              setIsLoading(true);
              setRetryKey((current) => current + 1);
            }}
            type="button"
          >
            重试
          </button>
        </div>
      )}

      {!isLoading && !error && conversations.length === 0 && (
        <p className="conversation-history__status">还没有历史会话。</p>
      )}

      {conversations.length > 0 && (
        <ul className="conversation-history__list">
          {conversations.map((conversation) => (
            <li key={conversation.id}>
              <button
                aria-pressed={selectedId === conversation.id}
                className={`conversation-history__item${selectedId === conversation.id ? " is-active" : ""}`}
                disabled={disabled}
                onClick={() => onSelect(conversation.id, getConversationLabel(conversation))}
                type="button"
              >
                <span className="conversation-history__item-title">
                  {getConversationLabel(conversation)}
                </span>
                <time dateTime={conversation.updated_at}>
                  {new Intl.DateTimeFormat("zh-CN", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(conversation.updated_at))}
                </time>
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && conversations.length > 0 && (
        <p className="conversation-history__error" role="alert">
          {error}
        </p>
      )}

      {hasMore && (
        <button
          className="button button--outline conversation-history__more"
          disabled={isLoadingMore}
          onClick={() => void loadMore()}
          type="button"
        >
          {isLoadingMore ? "正在加载…" : "加载更多会话"}
        </button>
      )}
    </section>
  );
}

interface ConversationBatch {
  items: ConversationSummary[];
  offset: number;
  hasMore: boolean;
}

async function loadConversationBatch(
  startOffset: number,
  skillCode?: string,
): Promise<ConversationBatch> {
  const items: ConversationSummary[] = [];
  let offset = startOffset;
  let hasMore = true;

  while (hasMore && items.length === 0) {
    const page = await listConversations(offset);
    items.push(...page.items.filter((item) => !skillCode || item.skill_code === skillCode));
    offset += page.items.length;
    hasMore = page.items.length === page.limit;
  }

  return { items, offset, hasMore };
}
