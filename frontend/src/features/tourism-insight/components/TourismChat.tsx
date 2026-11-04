import { useEffect, useState, type FormEvent } from "react";

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

/** 文旅洞察自由输入对话框，消息由现有会话 API 保存。 */
export function TourismChat({ conversationId, enabled, onResults }: TourismChatProps) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      setMessages((current) => current.filter((item) => item.id !== "local-assistant"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="tourism-chat" aria-label={t("文旅洞察对话")}>
      <h2 className="tourism-chat__title">文旅洞察助手</h2>
      <div className="tourism-chat__messages" aria-live="polite">
        {messages.length === 0 && (
          <p className="tourism-empty">
            输入游客评论或景区服务体验，智能体会提取证据并匹配评分子项。
          </p>
        )}
        {messages.map((message) => (
          <article
            className={`tourism-chat__message tourism-chat__message--${message.role}`}
            key={message.id}
          >
            <strong>{message.role === "user" ? "你" : "文旅洞察"}</strong>
            {message.content.parts
              .filter((part) => part.type === "text")
              .map((part, index) => (
                <p key={`${message.id}-${index}`}>{part.type === "text" ? part.text : ""}</p>
              ))}
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
        <textarea
          aria-label={t("输入游客评论")}
          disabled={!enabled || busy}
          maxLength={20_000}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={enabled ? t("输入游客评论或景区服务体验…") : t("请先导入评分规则")}
          value={draft}
        />
        <button
          className="button button--primary"
          disabled={!enabled || !draft.trim() || busy}
          type="submit"
        >
          {busy ? t("分析中…") : t("发送")}
        </button>
      </form>
      <p className="tourism-chat__hint">
        {t("仅处理游客评论和景区服务体验；无关内容会收到业务范围提示。")}
      </p>
    </section>
  );
}
