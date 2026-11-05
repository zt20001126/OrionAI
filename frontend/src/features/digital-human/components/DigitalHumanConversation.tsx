import { useLayoutEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { t } from "../../../i18n/localeStore";
import type {
  ConversationMessage,
  QuestionAnswersContentPart,
  QuestionContentPart,
} from "../../conversations/conversationApi";
import { CompletedQuestionCard, QuestionAnswerCard } from "../../conversations/QuestionAnswerCards";
import { QuestionWizard } from "../../conversations/QuestionWizard";

interface DigitalHumanConversationProps {
  messages: ConversationMessage[];
  pendingMessage: string | null;
  pendingQuestionMessageId: string | null;
  currentQuestionIndex: number;
  selectedAnswers: Record<string, string>;
  streamedAssistantText: string;
  onQuestionAnswerSelect: (questionId: string, answer: string) => void;
  onQuestionNext: () => void;
  onQuestionPrevious: () => void;
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

/** 获取消息中已提交的题卡答案；输入为会话消息，输出供已答卡片展示。 */
function getQuestionAnswersPart(message: ConversationMessage): QuestionAnswersContentPart | null {
  return (
    message.content.parts.find(
      (part): part is QuestionAnswersContentPart => part.type === "question_answers",
    ) ?? null
  );
}

/** 展示当前会话的消息流，只保留消息加载反馈，不在聊天区重复显示智能体状态。 */
export function DigitalHumanConversation({
  messages,
  pendingMessage,
  pendingQuestionMessageId,
  currentQuestionIndex,
  selectedAnswers,
  streamedAssistantText,
  onQuestionAnswerSelect,
  onQuestionNext,
  onQuestionPrevious,
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
      {messages.map((message, index) => {
        const text = getText(message);
        const questionPart = getQuestionPart(message);
        const questionAnswersPart = getQuestionAnswersPart(message);
        const isPendingQuestion = pendingQuestionMessageId === message.id;
        const nextMessage = messages[index + 1];
        const hasSubmittedQuestionAnswers =
          questionPart !== null &&
          nextMessage?.role === "user" &&
          (getQuestionAnswersPart(nextMessage) !== null ||
            getText(nextMessage).startsWith("用户已提交以下选择："));
        if (!text && !questionPart && !questionAnswersPart) return null;
        return (
          <article
            className={`digital-human-message digital-human-message--${message.role}${questionPart ? " digital-human-message--question" : ""}${questionAnswersPart ? " digital-human-message--question-answers" : ""}`}
            key={message.id}
          >
            {text && !questionAnswersPart && (
              <div className="digital-human-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
              </div>
            )}
            {questionAnswersPart && <QuestionAnswerCard items={questionAnswersPart.items} />}
            {questionPart && isPendingQuestion && (
              <QuestionWizard
                currentIndex={currentQuestionIndex}
                isSubmitting={isSubmitting}
                messageId={message.id}
                onNext={onQuestionNext}
                onPrevious={onQuestionPrevious}
                onSelect={onQuestionAnswerSelect}
                onSubmit={onQuestionSubmit}
                questions={questionPart.questions}
                selectedAnswers={selectedAnswers}
              />
            )}
            {questionPart &&
              !isPendingQuestion &&
              (hasSubmittedQuestionAnswers ? (
                <CompletedQuestionCard questions={questionPart.questions} />
              ) : (
                <div className="question-card__history" role="status">
                  {t("此题卡当前不等待答题。")}
                </div>
              ))}
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
