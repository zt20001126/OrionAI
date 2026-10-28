import { useEffect, useRef, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import {
  getConversationErrorMessage,
  listConversations,
  type ConversationSummary,
} from "./conversationApi";

const MAX_HISTORY_PAGE_SIZE = 100;
const HISTORY_PAGE_SIZE_FALLBACK = 10;
const VISIBLE_PAGE_COUNT = 5;

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

function getPageNumbers(currentPage: number, totalPages: number): number[] {
  const pageCount = Math.min(VISIBLE_PAGE_COUNT, totalPages);
  const firstPage = Math.min(
    Math.max(1, currentPage - Math.floor(pageCount / 2)),
    totalPages - pageCount + 1,
  );
  return Array.from({ length: pageCount }, (_, index) => firstPage + index);
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
  const [totalCount, setTotalCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const historyRef = useRef<HTMLElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const paginationRef = useRef<HTMLElement>(null);
  const { showToast } = useToast();
  const isPage = variant === "page";

  useEffect(() => {
    if (!isPage) return;

    let animationFrame = 0;
    const measurePageSize = () => {
      const history = historyRef.current;
      const page = history?.closest<HTMLElement>(".sessions-page");
      const header = page?.querySelector<HTMLElement>(".sessions-page__header");
      if (!history || !page || !header || page.clientHeight === 0) {
        setPageSize((current) =>
          current === HISTORY_PAGE_SIZE_FALLBACK ? current : HISTORY_PAGE_SIZE_FALLBACK,
        );
        return;
      }

      const pageStyle = window.getComputedStyle(page);
      const historyStyle = window.getComputedStyle(history);
      const list = history.querySelector<HTMLUListElement>(".conversation-history__list");
      const row = list?.querySelector<HTMLElement>(".conversation-history__item");
      const listGap =
        Number.parseFloat(list ? window.getComputedStyle(list).rowGap : "") ||
        Number.parseFloat(
          window.getComputedStyle(document.documentElement).getPropertyValue("--space-1"),
        ) ||
        0;
      const rowHeight = Number.parseFloat(
        row
          ? window.getComputedStyle(row).minHeight
          : historyStyle.getPropertyValue("--history-row-height"),
      );
      const pageGap = Number.parseFloat(pageStyle.rowGap) || 0;
      const historyGap = Number.parseFloat(historyStyle.rowGap) || 0;
      const paginationHeight = paginationRef.current?.offsetHeight ?? 0;
      const availablePanelHeight = page.clientHeight - header.offsetHeight - pageGap;
      const availableListHeight =
        availablePanelHeight -
        Number.parseFloat(historyStyle.paddingTop) -
        Number.parseFloat(historyStyle.paddingBottom) -
        Number.parseFloat(historyStyle.borderTopWidth) -
        Number.parseFloat(historyStyle.borderBottomWidth) -
        historyGap -
        paginationHeight;
      const measuredPageSize = Math.min(
        MAX_HISTORY_PAGE_SIZE,
        Math.max(1, Math.floor((availableListHeight + listGap) / (rowHeight + listGap))),
      );

      setPageSize((current) => (current === measuredPageSize ? current : measuredPageSize));
    };
    const scheduleMeasurement = () => {
      window.cancelAnimationFrame(animationFrame);
      animationFrame = window.requestAnimationFrame(measurePageSize);
    };

    const page = historyRef.current?.closest<HTMLElement>(".sessions-page");
    const header = page?.querySelector<HTMLElement>(".sessions-page__header");
    const resizeObserver =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(scheduleMeasurement);
    if (page) resizeObserver?.observe(page);
    if (header) resizeObserver?.observe(header);
    window.addEventListener("resize", scheduleMeasurement);
    scheduleMeasurement();

    return () => {
      window.cancelAnimationFrame(animationFrame);
      window.removeEventListener("resize", scheduleMeasurement);
      resizeObserver?.disconnect();
    };
  }, [isPage]);

  useEffect(() => {
    if (isPage && pageSize === 0) return;
    let isActive = true;

    async function loadHistory() {
      try {
        if (isPage) {
          let response = await listConversations((currentPage - 1) * pageSize, pageSize);
          if (!isActive) return;

          const lastPage = Math.max(1, Math.ceil(response.total_count / pageSize));
          setTotalCount(response.total_count);
          if (currentPage > lastPage) {
            setCurrentPage(lastPage);
            response = await listConversations((lastPage - 1) * pageSize, pageSize);
            if (!isActive) return;
            setTotalCount(response.total_count);
          }

          setConversations(response.items);
          setOffset(response.offset);
          setHasMore(false);
          setError(null);
          return;
        }

        const batch = await loadConversationBatch(0, skillCode);
        if (!isActive) return;
        setConversations(batch.items);
        setOffset(batch.offset);
        setHasMore(batch.hasMore);
        setError(null);
      } catch (requestError) {
        if (!isActive) return;
        const message = getConversationErrorMessage(requestError);
        setError(message);
        if (isPage) showToast("error", message);
      } finally {
        if (isActive) setIsLoading(false);
      }
    }

    void loadHistory();
    return () => {
      isActive = false;
    };
  }, [currentPage, isPage, pageSize, retryKey, showToast, skillCode]);

  async function loadMore() {
    setIsLoadingMore(true);
    setError(null);
    try {
      const batch = await loadConversationBatch(offset, skillCode);
      setConversations((current) => [...current, ...batch.items]);
      setOffset(batch.offset);
      setHasMore(batch.hasMore);
    } catch (requestError) {
      showToast("error", getConversationErrorMessage(requestError));
    } finally {
      setIsLoadingMore(false);
    }
  }

  function goToPage(page: number) {
    if (page === currentPage || isLoading) return;
    if (listRef.current) listRef.current.scrollTop = 0;
    setError(null);
    setIsLoading(true);
    setCurrentPage(page);
  }

  const totalPages = pageSize > 0 ? Math.ceil(totalCount / pageSize) : 0;
  const showPagination = isPage && totalCount > pageSize;

  return (
    <section
      aria-label={isPage ? "会话列表" : undefined}
      aria-labelledby={isPage ? undefined : `conversation-history-title-${variant}`}
      className={`conversation-history conversation-history--${variant}${showPagination ? " is-paginated" : ""}`}
      ref={historyRef}
    >
      {!isPage && (
        <div className="conversation-history__heading">
          <h2 id={`conversation-history-title-${variant}`}>
            {variant === "sidebar" ? "历史会话" : "所有会话"}
          </h2>
        </div>
      )}

      {isLoading && (
        <p className="conversation-history__status" role="status">
          正在加载会话…
        </p>
      )}

      {!isLoading && error && (isPage || conversations.length === 0) && (
        <div className="conversation-history__empty">
          <p role={isPage ? undefined : "alert"}>{error}</p>
          <button
            className="button button--outline"
            onClick={() => {
              setError(null);
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

      {!isLoading && !error && conversations.length > 0 && (
        <ul className="conversation-history__list" ref={listRef}>
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

      {!isPage && error && conversations.length > 0 && (
        <p className="conversation-history__error" role="alert">
          {error}
        </p>
      )}

      {!isPage && hasMore && (
        <button
          className="button button--outline conversation-history__more"
          disabled={isLoadingMore}
          onClick={() => void loadMore()}
          type="button"
        >
          {isLoadingMore ? "正在加载…" : "加载更多会话"}
        </button>
      )}

      {isPage && (totalCount > 0 || isLoading) && (
        <footer
          aria-hidden={totalCount === 0 || undefined}
          className={`conversation-history__pagination${totalCount === 0 ? " is-placeholder" : ""}`}
          ref={paginationRef}
        >
          {totalCount > 0 && (
            <span className="conversation-history__pagination-total">共 {totalCount} 条会话</span>
          )}
          {showPagination && (
            <nav aria-label="会话记录分页" className="conversation-history__pagination-nav">
              <button
                aria-label="上一页"
                className="conversation-history__page-button conversation-history__page-arrow"
                disabled={currentPage === 1 || isLoading}
                onClick={() => goToPage(currentPage - 1)}
                type="button"
              >
                ‹
              </button>
              <div className="conversation-history__page-list">
                {getPageNumbers(currentPage, totalPages).map((page) => (
                  <button
                    aria-current={currentPage === page ? "page" : undefined}
                    className={`conversation-history__page-button${currentPage === page ? " is-current" : ""}`}
                    disabled={isLoading}
                    key={page}
                    onClick={() => goToPage(page)}
                    type="button"
                  >
                    {page}
                  </button>
                ))}
              </div>
              <button
                aria-label="下一页"
                className="conversation-history__page-button conversation-history__page-arrow"
                disabled={currentPage === totalPages || isLoading}
                onClick={() => goToPage(currentPage + 1)}
                type="button"
              >
                ›
              </button>
            </nav>
          )}
        </footer>
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
