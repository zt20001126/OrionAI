import { useLayoutEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { t } from "../../../i18n/localeStore";
import type { ConversationMessage } from "../../conversations/conversationApi";

interface DigitalHumanConversationProps {
  messages: ConversationMessage[];
  pendingMessage: string | null;
  streamedAssistantText: string;
  isLoading: boolean;
}

function getText(message: ConversationMessage): string {
  return message.content.parts
    .filter(
      (part): part is Extract<(typeof message.content.parts)[number], { type: "text" }> =>
        part.type === "text",
    )
    .map((part) => part.text)
    .join("\n");
}

/** 展示当前会话的消息流，只保留消息加载反馈，不在聊天区重复显示智能体状态。 */
export function DigitalHumanConversation({
  messages,
  pendingMessage,
  streamedAssistantText,
  isLoading,
}: DigitalHumanConversationProps) {
  const messageListRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const messageList = messageListRef.current;
    if (messageList) messageList.scrollTop = messageList.scrollHeight;
  }, [isLoading, messages, pendingMessage, streamedAssistantText]);

  return (
    <div
      aria-label={t("对话消息")}
      className="digital-human-messages"
      role="log"
      aria-live="polite"
      ref={messageListRef}
    >
      {messages.map((message) => {
        const text = getText(message);
        if (!text) return null;
        return (
          <article
            className={`digital-human-message digital-human-message--${message.role}`}
            key={message.id}
          >
            <div className="digital-human-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
            </div>
          </article>
        );
      })}
      {pendingMessage && (
        <article
          aria-label={t("正在发送的消息")}
          className="digital-human-message digital-human-message--user digital-human-message--pending"
        >
          <div className="digital-human-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{pendingMessage}</ReactMarkdown>
          </div>
        </article>
      )}
      {streamedAssistantText && (
        <article
          aria-label={t("助手回答")}
          className="digital-human-message digital-human-message--assistant digital-human-message--streaming"
        >
          <div className="digital-human-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamedAssistantText}</ReactMarkdown>
          </div>
        </article>
      )}
      {isLoading && (
        <p className="digital-human-message-status" role="status">
          {t("正在加载对话…")}
        </p>
      )}
    </div>
  );
}
