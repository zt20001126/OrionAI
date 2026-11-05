import { useLayoutEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { t } from "../../../i18n/localeStore";
import type { ConversationMessage, QuestionContentPart } from "../../conversations/conversationApi";
import { DigitalHumanQuestionCard } from "./DigitalHumanQuestionCard";

interface DigitalHumanConversationProps {
  messages: ConversationMessage[];
  pendingMessage: string | null;
  pendingQuestionMessageId: string | null;
  selectedAnswers: Record<string, string>;
  streamedAssistantText: string;
  onQuestionAnswerSelect: (questionId: string, answer: string) => void;
  onQuestionSubmit: () => void;
  isSubmitting: boolean;
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

function getQuestionPart(message: ConversationMessage): QuestionContentPart | null {
  return (
    message.content.parts.find((part): part is QuestionContentPart => part.type === "question") ??
    null
  );
}

/** 展示当前会话的消息流，只保留消息加载反馈，不在聊天区重复显示智能体状态。 */
export function DigitalHumanConversation({
  messages,
  pendingMessage,
  pendingQuestionMessageId,
  selectedAnswers,
  streamedAssistantText,
  onQuestionAnswerSelect,
  onQuestionSubmit,
  isSubmitting,
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
        const questionPart = getQuestionPart(message);
        if (!text && !questionPart) return null;
        return (
          <article
            className={`digital-human-message digital-human-message--${message.role}${questionPart ? " digital-human-message--question" : ""}`}
            key={message.id}
          >
            {text && (
              <div className="digital-human-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
              </div>
            )}
            {questionPart && (
              <DigitalHumanQuestionCard
                isPending={pendingQuestionMessageId === message.id}
                isSubmitting={isSubmitting}
                messageId={message.id}
                onSelect={onQuestionAnswerSelect}
                onSubmit={onQuestionSubmit}
                questions={questionPart.questions}
                selectedAnswers={selectedAnswers}
              />
            )}
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
