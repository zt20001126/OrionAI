import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { PlatformIcon } from "../platform/PlatformIcon";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { ConversationHistory } from "./ConversationHistory";
import {
  createConversation,
  getConversationErrorMessage,
  listAllMessages,
  sendConversationMessage,
  submitQuestionAnswers,
  type ConversationMessage,
  type QuestionContentPart,
} from "./conversationApi";
import "./conversations.css";

interface ConversationPageProps {
  conversationId: string | null;
  onNavigate: (path: PlatformRoute) => void;
}

function getPendingQuestion(messages: ConversationMessage[]): {
  messageId: string;
  part: QuestionContentPart;
} | null {
  const latestMessage = messages.at(-1);
  if (latestMessage?.role !== "assistant") return null;

  const questionPart = latestMessage.content.parts.find(
    (part): part is QuestionContentPart => part.type === "question",
  );
  return questionPart ? { messageId: latestMessage.id, part: questionPart } : null;
}

function messageText(message: ConversationMessage): string {
  return message.content.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n");
}

export function ConversationPage({ conversationId, onNavigate }: ConversationPageProps) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [answerSelection, setAnswerSelection] = useState<{
    conversationId: string | null;
    answers: Record<string, string>;
  }>({ conversationId: null, answers: {} });
  const [loadedConversationId, setLoadedConversationId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [errorState, setErrorState] = useState<{
    conversationId: string | null;
    message: string;
  } | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const skipNextRouteLoad = useRef<string | null>(null);
  const messageLogRef = useRef<HTMLDivElement>(null);
  const visibleMessages = useMemo(
    () => (conversationId && loadedConversationId === conversationId ? messages : []),
    [conversationId, loadedConversationId, messages],
  );
  const selectedAnswers =
    answerSelection.conversationId === conversationId ? answerSelection.answers : {};
  const isLoading = Boolean(conversationId) && loadedConversationId !== conversationId;
  const error = errorState?.conversationId === conversationId ? errorState.message : null;

  useEffect(() => {
    if (!conversationId) return;

    if (skipNextRouteLoad.current === conversationId) {
      skipNextRouteLoad.current = null;
      return;
    }

    let isActive = true;
    void listAllMessages(conversationId)
      .then((loadedMessages) => {
        if (isActive) {
          setMessages(loadedMessages);
          setLoadedConversationId(conversationId);
          setErrorState((current) => (current?.conversationId === conversationId ? null : current));
        }
      })
      .catch((requestError: unknown) => {
        if (isActive) {
          setMessages([]);
          setLoadedConversationId(conversationId);
          setErrorState({
            conversationId,
            message: getConversationErrorMessage(requestError),
          });
        }
      });

    return () => {
      isActive = false;
    };
  }, [conversationId]);

  useEffect(() => {
    const log = messageLogRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [visibleMessages, pendingText]);

  const pendingQuestion = useMemo(() => getPendingQuestion(visibleMessages), [visibleMessages]);
  const canSubmitAnswers =
    pendingQuestion !== null &&
    pendingQuestion.part.questions.every((question) => Boolean(selectedAnswers[question.id]));

  async function refreshMessages(activeConversationId: string): Promise<void> {
    const refreshedMessages = await listAllMessages(activeConversationId);
    setMessages(refreshedMessages);
    setLoadedConversationId(activeConversationId);
  }

  async function handleReloadMessages() {
    if (!conversationId) return;
    setLoadedConversationId(null);
    setErrorState(null);
    try {
      await refreshMessages(conversationId);
    } catch (requestError) {
      setLoadedConversationId(conversationId);
      setErrorState({
        conversationId,
        message: getConversationErrorMessage(requestError),
      });
    }
  }

  async function handleSend(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || isSubmitting || isLoading || pendingQuestion) return;

    setIsSubmitting(true);
    setPendingText(text);
    setErrorState(null);
    let activeConversationId = conversationId;
    let createdThisTurn = false;

    try {
      if (!activeConversationId) {
        const conversation = await createConversation();
        activeConversationId = conversation.id;
        createdThisTurn = true;
      }

      await sendConversationMessage(activeConversationId, text);
      await refreshMessages(activeConversationId);
      setDraft("");
      setHistoryRefreshKey((current) => current + 1);
      if (createdThisTurn) {
        skipNextRouteLoad.current = activeConversationId;
        onNavigate(`${platformPaths.chat}/${activeConversationId}`);
      }
    } catch (requestError) {
      setErrorState({
        conversationId: activeConversationId,
        message: getConversationErrorMessage(requestError),
      });
      if (activeConversationId) {
        try {
          await refreshMessages(activeConversationId);
        } catch {
          // 保留原始提交错误；稍后可通过重新加载按钮恢复消息。
        }
        setHistoryRefreshKey((current) => current + 1);
        if (createdThisTurn) {
          skipNextRouteLoad.current = activeConversationId;
          onNavigate(`${platformPaths.chat}/${activeConversationId}`);
        }
      }
    } finally {
      setPendingText(null);
      setIsSubmitting(false);
    }
  }

  async function handleSubmitAnswers() {
    if (!conversationId || !pendingQuestion || !canSubmitAnswers || isSubmitting) return;

    setIsSubmitting(true);
    setErrorState(null);
    try {
      await submitQuestionAnswers(conversationId, selectedAnswers);
      await refreshMessages(conversationId);
      setAnswerSelection({ conversationId, answers: {} });
      setHistoryRefreshKey((current) => current + 1);
    } catch (requestError) {
      setErrorState({
        conversationId,
        message: getConversationErrorMessage(requestError),
      });
      try {
        await refreshMessages(conversationId);
      } catch {
        // 保留原始提交错误，避免错误提示被刷新失败覆盖。
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  }

  return (
    <div className="conversation-page">
      <aside aria-label="历史会话导航" className="conversation-page__history">
        <button
          className="button button--outline conversation-page__new"
          disabled={isSubmitting}
          onClick={() => onNavigate(platformPaths.chat)}
          type="button"
        >
          <span aria-hidden="true">+</span>
          新建对话
        </button>
        <ConversationHistory
          disabled={isSubmitting}
          key={historyRefreshKey}
          onSelect={(id) => onNavigate(`${platformPaths.chat}/${id}`)}
          selectedId={conversationId}
          variant="sidebar"
        />
      </aside>

      <section aria-label="通用对话助手" className="conversation-panel">
        {conversationId && (
          <header className="conversation-panel__header">
            <h1>通用对话助手</h1>
            <span>多轮对话</span>
          </header>
        )}

        <div
          aria-label="对话消息"
          aria-live="polite"
          className="conversation-messages"
          ref={messageLogRef}
          role="log"
        >
          {!conversationId && visibleMessages.length === 0 && (
            <div className="conversation-empty">
              <span aria-hidden="true" className="conversation-empty__icon">
                <PlatformIcon name="assistant" size={24} />
              </span>
              <h1>通用对话助手</h1>
              <p>有什么问题，尽管问我。</p>
            </div>
          )}

          {isLoading && (
            <p className="conversation-status" role="status">
              正在加载对话…
            </p>
          )}

          {!isLoading && !error && conversationId && visibleMessages.length === 0 && (
            <p className="conversation-status">发送第一条消息，开始这段对话。</p>
          )}

          {error && (
            <div className="conversation-error" role="alert">
              <span>{error}</span>
              {conversationId && (
                <button
                  className="button button--outline"
                  onClick={() => void handleReloadMessages()}
                  type="button"
                >
                  重新加载消息
                </button>
              )}
            </div>
          )}

          {!isLoading && error && visibleMessages.length === 0 && conversationId && (
            <p className="conversation-status">暂时无法显示此会话内容。</p>
          )}

          {visibleMessages.map((message) => {
            const questionPart = message.content.parts.find(
              (part): part is QuestionContentPart => part.type === "question",
            );
            const isCurrentQuestion = pendingQuestion?.messageId === message.id;
            const text = messageText(message);

            return (
              <article
                className={`conversation-message conversation-message--${message.role}`}
                key={message.id}
              >
                <div className="conversation-message__label">
                  {message.role === "user" ? "你" : "通用对话助手"}
                </div>
                {text && <p className="conversation-message__text">{text}</p>}
                {questionPart && (
                  <div className="question-card">
                    {questionPart.questions.map((question) => (
                      <fieldset
                        className="question-card__question"
                        disabled={!isCurrentQuestion || isSubmitting}
                        key={question.id}
                      >
                        <legend>{question.title}</legend>
                        {question.options.map((option) => (
                          <label className="question-card__option" key={option.label}>
                            <input
                              checked={
                                isCurrentQuestion && selectedAnswers[question.id] === option.label
                              }
                              name={`question-${message.id}-${question.id}`}
                              onChange={() =>
                                setAnswerSelection((current) => ({
                                  conversationId,
                                  answers: {
                                    ...(current.conversationId === conversationId
                                      ? current.answers
                                      : {}),
                                    [question.id]: option.label,
                                  },
                                }))
                              }
                              type="radio"
                              value={option.label}
                            />
                            <span>
                              <strong>{option.label}</strong>
                              <small>{option.description}</small>
                            </span>
                          </label>
                        ))}
                      </fieldset>
                    ))}
                    {isCurrentQuestion && (
                      <div className="question-card__footer">
                        <p>请先完成当前题卡，再发送新消息。</p>
                        <button
                          className="button button--primary"
                          disabled={!canSubmitAnswers || isSubmitting}
                          onClick={() => void handleSubmitAnswers()}
                          type="button"
                        >
                          {isSubmitting ? "正在提交…" : "提交选择"}
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </article>
            );
          })}

          {pendingText && (
            <article
              aria-label="正在发送的消息"
              className="conversation-message conversation-message--user conversation-message--pending"
            >
              <div className="conversation-message__label">你</div>
              <p className="conversation-message__text">{pendingText}</p>
            </article>
          )}

          {isSubmitting && (
            <p className="conversation-status" role="status">
              助手正在回复…
            </p>
          )}
        </div>

        <form className="conversation-composer" onSubmit={(event) => void handleSend(event)}>
          <label className="conversation-visually-hidden" htmlFor="conversation-message-input">
            发送消息
          </label>
          <textarea
            id="conversation-message-input"
            disabled={isSubmitting || isLoading || Boolean(pendingQuestion)}
            maxLength={20_000}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder={
              pendingQuestion ? "请先完成题卡选择。" : "输入消息，Enter 发送，Shift + Enter 换行"
            }
            value={draft}
          />
          <div className="conversation-composer__footer">
            <span>{error ? "检查消息状态后再决定是否重试。" : "回答以完整消息形式返回。"}</span>
            <button
              aria-label="发送消息"
              className="button button--primary conversation-composer__send"
              disabled={!draft.trim() || isSubmitting || isLoading || Boolean(pendingQuestion)}
              type="submit"
            >
              <PlatformIcon name="arrow" size={16} />
              发送
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
