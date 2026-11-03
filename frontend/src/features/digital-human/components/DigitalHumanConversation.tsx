import { t } from "../../../i18n/localeStore";
import type { ConversationMessage } from "../../conversations/conversationApi";

interface DigitalHumanConversationProps {
  messages: ConversationMessage[];
  pendingMessage: string | null;
  streamedAssistantText: string;
  isLoading: boolean;
  isThinking: boolean;
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

export function DigitalHumanConversation({
  messages,
  pendingMessage,
  streamedAssistantText,
  isLoading,
  isThinking,
}: DigitalHumanConversationProps) {
  return (
    <div
      aria-label={t("对话消息")}
      className="digital-human-messages"
      role="log"
      aria-live="polite"
    >
      {messages.map((message) => {
        const text = getText(message);
        if (!text) return null;
        return (
          <article
            className={`digital-human-message digital-human-message--${message.role}`}
            key={message.id}
          >
            <p>{text}</p>
          </article>
        );
      })}
      {pendingMessage && (
        <article
          aria-label={t("正在发送的消息")}
          className="digital-human-message digital-human-message--user digital-human-message--pending"
        >
          <p>{pendingMessage}</p>
        </article>
      )}
      {streamedAssistantText && (
        <article
          aria-label={t("助手回答")}
          className="digital-human-message digital-human-message--assistant digital-human-message--streaming"
        >
          <p>{streamedAssistantText}</p>
        </article>
      )}
      {isLoading && (
        <p className="digital-human-message-status" role="status">
          {t("正在加载对话…")}
        </p>
      )}
      {!isLoading && messages.length === 0 && !pendingMessage && !streamedAssistantText && (
        <p className="digital-human-message-status">{t("开始一段文字或语音对话。")}</p>
      )}
      {isThinking && (
        <p className="digital-human-message-status" role="status">
          {t("数字人正在思考…")}
        </p>
      )}
    </div>
  );
}
