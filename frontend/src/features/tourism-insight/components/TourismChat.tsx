import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { PlatformIcon } from "../../platform/PlatformIcon";
import {
  listMessages,
  streamConversationMessage,
  type ConversationMessage,
} from "../../conversations/conversationApi";
import { t } from "../../../i18n/localeStore";

interface TourismChatProps {
  conversationId: string;
  enabled: boolean;
  onResults: () => void;
}

/** 评分依据助手自由输入对话框，消息由现有会话 API 保存。 */
export function TourismChat({ conversationId, enabled, onResults }: TourismChatProps) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const shouldStickToBottomRef = useRef(true);
  const focusAfterSendRef = useRef(false);

  useLayoutEffect(() => {
    const messageList = messageListRef.current;
    if (messageList && shouldStickToBottomRef.current) {
      messageList.scrollTop = messageList.scrollHeight;
    }
  }, [messages, busy, error]);

  useEffect(() => {
    if (!busy && focusAfterSendRef.current) {
      inputRef.current?.focus();
      focusAfterSendRef.current = false;
    }
  }, [busy]);

  useEffect(() => {
    const input = inputRef.current;
    if (input) {
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
    }
  }, [draft]);

  useEffect(() => {
    let active = true;
    void listMessages(conversationId)
      .then((page) => {
        if (active) setMessages(page.items);
      })
      .catch((requestError: unknown) => {
        if (active)
          setError(requestError instanceof Error ? requestError.message : "对话记录加载失败。");
      });
    return () => {
      active = false;
    };
  }, [conversationId]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy || !enabled) return;
    shouldStickToBottomRef.current = true;
    focusAfterSendRef.current = true;
    setDraft("");
    setBusy(true);
    setError(null);
    const userMessage: ConversationMessage = {
      id: `local-${Date.now()}`,
      conversation_id: conversationId,
      role: "user",
      content: { parts: [{ type: "text", text }] },
      created_at: new Date().toISOString(),
    };
    setMessages((current) => [...current, userMessage]);
    let answer = "";
    try {
      const finalMessage = await streamConversationMessage(
        conversationId,
        text,
        (delta) => {
          answer += delta;
          setMessages((current) => {
            const last = current.at(-1);
            const assistantMessage: ConversationMessage = {
              id: "local-assistant",
              conversation_id: conversationId,
              role: "assistant",
              content: { parts: [{ type: "text", text: answer }] },
              created_at: new Date().toISOString(),
            };
            return last?.role === "assistant" && last.id === "local-assistant"
              ? [...current.slice(0, -1), assistantMessage]
              : [...current, assistantMessage];
          });
        },
        new AbortController().signal,
      );
      if (finalMessage) {
        setMessages((current) => [
          ...current.filter((item) => item.id !== "local-assistant"),
          finalMessage,
        ]);
      }
      onResults();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "消息发送失败。");
      setDraft(text);
      setMessages((current) => current.filter((item) => item.id !== "local-assistant"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="tourism-chat" aria-label={t("评分依据助手对话")}>
      <h2 className="tourism-chat__title">
        <PlatformIcon name="assistant" size={20} />
        <span>{t("评分依据助手")}</span>
      </h2>
      <div
        aria-label={t("对话消息")}
        aria-live="polite"
        className="tourism-chat__messages"
        onScroll={(event) => {
          const element = event.currentTarget;
          shouldStickToBottomRef.current =
            element.scrollHeight - element.scrollTop - element.clientHeight < 48;
        }}
        ref={messageListRef}
        role="log"
      >
        {messages.length === 0 && !busy && (
          <p className="tourism-chat__empty">{t("输入评论，快速查找对应评分依据。")}</p>
        )}
        {messages.map((message) => (
          <article
            className={`tourism-chat__message tourism-chat__message--${message.role}`}
            key={message.id}
          >
            <div className="tourism-chat__markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content.parts
                  .filter((part) => part.type === "text")
                  .map((part) => part.text)
                  .join("\n")}
              </ReactMarkdown>
            </div>
          </article>
        ))}
        {busy && (
          <p className="tourism-chat__status" role="status">
            正在分析评论并匹配评分规则…
          </p>
        )}
        {error && (
          <p className="tourism-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <form className="tourism-chat__composer" onSubmit={(event) => void submit(event)}>
        <div className="tourism-chat__input-container">
          <textarea
            aria-label={t("输入游客评论")}
            disabled={!enabled || busy}
            maxLength={20_000}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={t("输入游客评论，查找对应评分依据...")}
            ref={inputRef}
            rows={2}
            value={draft}
          />
          <button
            aria-label={t("发送")}
            className="tourism-chat__send button button--primary"
            disabled={!enabled || !draft.trim() || busy}
            type="submit"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M12 19V5m-7 7 7-7 7 7" />
            </svg>
          </button>
        </div>
      </form>
    </section>
  );
}
