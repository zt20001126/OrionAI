import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

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

interface QuestionAnswerSummaryItem {
  question: string;
  answer: string;
}

interface QuestionAnswerSummaryData {
  count: number;
  items: QuestionAnswerSummaryItem[];
  detailsUnavailable: boolean;
}

function getQuestionPart(message: ConversationMessage | undefined): QuestionContentPart | null {
  if (message?.role !== "assistant") return null;

  return (
    message.content.parts.find((part): part is QuestionContentPart => part.type === "question") ??
    null
  );
}

function getQuestionAnswerSummary(
  text: string,
  questionPart?: QuestionContentPart | null,
): QuestionAnswerSummaryData | null {
  const answerHeader = "用户已提交以下选择：";
  if (text.startsWith(answerHeader)) {
    if (questionPart) {
      const lines = text.split(/\r?\n/);
      const items = questionPart.questions.map((question) => {
        const fullWidthPrefix = `- ${question.title}：`;
        const asciiPrefix = `- ${question.title}:`;
        const answerLine = lines.find(
          (line) => line.startsWith(fullWidthPrefix) || line.startsWith(asciiPrefix),
        );
        if (!answerLine) return null;

        const prefix = answerLine.startsWith(fullWidthPrefix) ? fullWidthPrefix : asciiPrefix;
        const answer = answerLine.slice(prefix.length).trim();
        return answer ? { question: question.title, answer } : null;
      });

      if (items.every((item): item is QuestionAnswerSummaryItem => item !== null)) {
        return { count: items.length, items, detailsUnavailable: false };
      }
    }

    const formattedAnswerCount = text
      .split(/\r?\n/)
      .filter((line) => /^- .+[:：].+$/u.test(line)).length;
    if (formattedAnswerCount > 0) {
      return { count: formattedAnswerCount, items: [], detailsUnavailable: true };
    }
  }

  const legacyPrefix = "已提交选择：";
  if (!text.startsWith(legacyPrefix)) return null;

  try {
    const parsed: unknown = JSON.parse(text.slice(legacyPrefix.length));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;

    const values = Object.values(parsed as Record<string, unknown>);
    if (values.length === 0 || !values.every((value) => typeof value === "string")) return null;
    return { count: values.length, items: [], detailsUnavailable: true };
  } catch {
    return null;
  }
}

interface QuestionWizardProps {
  currentIndex: number;
  isSubmitting: boolean;
  messageId: string;
  onNext: () => void;
  onPrevious: () => void;
  onSelect: (questionId: string, answer: string) => void;
  onSubmit: () => void;
  questions: QuestionContentPart["questions"];
  selectedAnswers: Record<string, string>;
}

function QuestionWizard({
  currentIndex,
  isSubmitting,
  messageId,
  onNext,
  onPrevious,
  onSelect,
  onSubmit,
  questions,
  selectedAnswers,
}: QuestionWizardProps) {
  const question = questions[currentIndex];
  if (!question) return null;

  const hasSteps = questions.length > 1;
  const hasAnswer = Boolean(selectedAnswers[question.id]);
  const isLastQuestion = currentIndex === questions.length - 1;

  return (
    <section aria-label="问题答题卡" className="question-card">
      <header className="question-card__header">
        <strong>需要你的选择</strong>
        {hasSteps && (
          <span>
            第 {currentIndex + 1} / {questions.length} 题
          </span>
        )}
      </header>

      {hasSteps && (
        <div
          aria-label="答题进度"
          aria-valuemax={questions.length}
          aria-valuemin={1}
          aria-valuenow={currentIndex + 1}
          className="question-card__progress"
          role="progressbar"
        >
          <span style={{ width: `${((currentIndex + 1) / questions.length) * 100}%` }} />
        </div>
      )}

      <fieldset className="question-card__question" disabled={isSubmitting}>
        <legend>{question.title}</legend>
        {question.options.map((option) => (
          <label className="question-card__option" key={option.label}>
            <input
              checked={selectedAnswers[question.id] === option.label}
              name={`question-${messageId}-${question.id}`}
              onChange={() => onSelect(question.id, option.label)}
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

      <footer className="question-card__footer">
        {hasSteps && currentIndex > 0 ? (
          <button
            className="button button--outline"
            disabled={isSubmitting}
            onClick={onPrevious}
            type="button"
          >
            ← 上一题
          </button>
        ) : (
          <span />
        )}

        {isLastQuestion ? (
          <button
            className="button button--primary"
            disabled={isSubmitting || !questions.every((item) => selectedAnswers[item.id])}
            onClick={onSubmit}
            type="button"
          >
            {isSubmitting ? "正在提交…" : "提交答案"}
          </button>
        ) : (
          <button
            className="button button--primary"
            disabled={isSubmitting || !hasAnswer}
            onClick={onNext}
            type="button"
          >
            下一题 →
          </button>
        )}
      </footer>
    </section>
  );
}

function QuestionAnswerSummary({ summary }: { summary: QuestionAnswerSummaryData }) {
  return (
    <div aria-label="已提交回答摘要" className="conversation-answer-summary">
      <strong className="conversation-answer-summary__heading">
        <span aria-hidden="true">✓</span>
        已提交回答 · 共 {summary.count} 题
      </strong>
      {summary.items.map((item) => (
        <div className="conversation-answer-summary__item" key={item.question}>
          <span>{item.question}</span>
          <strong>{item.answer}</strong>
        </div>
      ))}
      {summary.detailsUnavailable && <p>历史消息未包含完整题目，暂时无法还原选择明细。</p>}
    </div>
  );
}

const markdownComponents: Components = {
  a: ({ href, title, children }) =>
    href ? (
      <a href={href} rel="noopener noreferrer" target="_blank" title={title}>
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
};

export function ConversationPage({ conversationId, onNavigate }: ConversationPageProps) {
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [answerSelection, setAnswerSelection] = useState<{
    conversationId: string | null;
    answers: Record<string, string>;
  }>({ conversationId: null, answers: {} });
  const [questionStep, setQuestionStep] = useState<{ messageId: string | null; index: number }>({
    messageId: null,
    index: 0,
  });
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
  const composerInputRef = useRef<HTMLTextAreaElement>(null);
  const composerSendButtonRef = useRef<HTMLButtonElement>(null);
  const shouldFollowMessagesRef = useRef(true);
  const shouldRestoreComposerFocusRef = useRef(false);
  const previousConversationIdRef = useRef(conversationId);
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

  useLayoutEffect(() => {
    const log = messageLogRef.current;
    if (!log) return;

    if (previousConversationIdRef.current !== conversationId) {
      previousConversationIdRef.current = conversationId;
      shouldFollowMessagesRef.current = true;
      log.scrollTop = 0;
    }

    if (
      shouldFollowMessagesRef.current &&
      (!conversationId || loadedConversationId === conversationId)
    ) {
      log.scrollTop = log.scrollHeight;
    }
  }, [conversationId, isSubmitting, loadedConversationId, pendingText, visibleMessages]);

  useLayoutEffect(() => {
    if (isSubmitting || !shouldRestoreComposerFocusRef.current) return;

    shouldRestoreComposerFocusRef.current = false;
    const input = composerInputRef.current;
    const activeElement = document.activeElement;
    const focusRemainsInComposer =
      activeElement === document.body ||
      activeElement === document.documentElement ||
      activeElement === input ||
      activeElement === composerSendButtonRef.current;

    if (input && !input.disabled && focusRemainsInComposer) input.focus();
  }, [isSubmitting]);

  useLayoutEffect(() => {
    const input = composerInputRef.current;
    if (!input) return;

    input.style.height = "auto";
    const maxHeight = 200;
    const minHeight = Number.parseFloat(window.getComputedStyle(input).minHeight) || 64;
    input.style.height = `${Math.min(Math.max(input.scrollHeight, minHeight), maxHeight)}px`;
    input.style.overflowY = input.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [draft]);

  const pendingQuestion = useMemo(() => getPendingQuestion(visibleMessages), [visibleMessages]);
  const currentQuestionIndex =
    pendingQuestion && questionStep.messageId === pendingQuestion.messageId
      ? Math.min(questionStep.index, pendingQuestion.part.questions.length - 1)
      : 0;
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

    const submitter = (event?.nativeEvent as SubmitEvent | undefined)?.submitter;
    shouldRestoreComposerFocusRef.current =
      document.activeElement === composerInputRef.current ||
      document.activeElement === composerSendButtonRef.current ||
      submitter === composerSendButtonRef.current;
    shouldFollowMessagesRef.current = true;
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
      setQuestionStep({ messageId: null, index: 0 });
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
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing ||
      event.keyCode === 229
    ) {
      return;
    }

    event.preventDefault();
    void handleSend();
  }

  function handleMessagesScroll() {
    const log = messageLogRef.current;
    if (!log) return;

    const distanceFromBottom = log.scrollHeight - log.scrollTop - log.clientHeight;
    shouldFollowMessagesRef.current = distanceFromBottom <= 96;
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
        <header className="conversation-panel__header">
          <h1>通用对话助手</h1>
          <span>多轮对话</span>
        </header>

        <div
          aria-label="对话消息"
          aria-live="polite"
          className="conversation-messages"
          onScroll={handleMessagesScroll}
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

          {visibleMessages.map((message, index) => {
            const questionPart = getQuestionPart(message);
            const isCurrentQuestion = pendingQuestion?.messageId === message.id;
            const text = messageText(message);
            const previousQuestionPart = getQuestionPart(visibleMessages[index - 1]);
            const answerSummary =
              message.role === "user" ? getQuestionAnswerSummary(text, previousQuestionPart) : null;
            const nextMessage = visibleMessages[index + 1];
            const hasSubmittedQuestionAnswers =
              questionPart !== null &&
              nextMessage?.role === "user" &&
              getQuestionAnswerSummary(messageText(nextMessage), questionPart) !== null;

            return (
              <article
                className={`conversation-message conversation-message--${message.role}`}
                key={message.id}
              >
                {message.role === "assistant" && text && (
                  <div className="conversation-message__bubble">
                    <div className="conversation-message__markdown">
                      <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                        {text}
                      </ReactMarkdown>
                    </div>
                  </div>
                )}
                {message.role === "user" &&
                  text &&
                  (answerSummary ? (
                    <QuestionAnswerSummary summary={answerSummary} />
                  ) : (
                    <p className="conversation-message__text">{text}</p>
                  ))}
                {questionPart && isCurrentQuestion && (
                  <QuestionWizard
                    currentIndex={currentQuestionIndex}
                    isSubmitting={isSubmitting}
                    messageId={message.id}
                    onNext={() =>
                      setQuestionStep({ messageId: message.id, index: currentQuestionIndex + 1 })
                    }
                    onPrevious={() =>
                      setQuestionStep({ messageId: message.id, index: currentQuestionIndex - 1 })
                    }
                    onSelect={(questionId, answer) =>
                      setAnswerSelection((current) => ({
                        conversationId,
                        answers: {
                          ...(current.conversationId === conversationId ? current.answers : {}),
                          [questionId]: answer,
                        },
                      }))
                    }
                    onSubmit={() => void handleSubmitAnswers()}
                    questions={questionPart.questions}
                    selectedAnswers={selectedAnswers}
                  />
                )}
                {questionPart && !isCurrentQuestion && (
                  <div
                    className={`question-card__history${hasSubmittedQuestionAnswers ? " is-complete" : ""}`}
                    role="status"
                  >
                    {hasSubmittedQuestionAnswers
                      ? `✓ 已完成答题 · 共 ${questionPart.questions.length} 题`
                      : "此题卡当前不等待答题。"}
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
            ref={composerInputRef}
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
              ref={composerSendButtonRef}
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
