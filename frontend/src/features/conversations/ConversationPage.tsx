import {
  useCallback,
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

import { useToast } from "../../components/ToastProvider";
import { PlatformIcon } from "../platform/PlatformIcon";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { ConversationHistory } from "./ConversationHistory";
import { CompletedQuestionCard, QuestionAnswerCard } from "./QuestionAnswerCards";
import { QuestionWizard } from "./QuestionWizard";
import {
  createConversation,
  getActiveConversationRun,
  getConversationErrorMessage,
  interruptConversationRun,
  listenConversationRun,
  listAllMessages,
  listConversations,
  startConversationMessageRun,
  startQuestionAnswersRun,
  DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER,
  DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID,
  type ConversationMessage,
  type ImageResultContentPart,
  type MessageListResponse,
  type QuestionContentPart,
  type QuestionAnswersContentPart,
  type SubmittedQuestionAnswer,
  type UserLocationContext,
} from "./conversationApi";
import "./conversations.css";
import { t } from "../../i18n/localeStore";

interface ConversationPageProps {
  conversationId: string | null;
  embedded?: boolean;
  panelOpen?: boolean;
  onCollapsePanel?: () => void;
  onConversationIdChange?: (conversationId: string | null) => void;
  onResumeSaved?: () => void | Promise<void>;
  onNavigate: (path: PlatformRoute) => void;
}

const RESUME_ASSISTANT_PROMPTS = [
  { label: "优化简历表达", prompt: "请帮我优化简历表达，让内容更清晰专业。" },
  { label: "改写项目经历", prompt: "请帮我改写简历中的项目经历，突出我的贡献和成果。" },
  { label: "匹配岗位要求", prompt: "请根据目标岗位要求分析我的简历匹配度。" },
] as const;
const LOCATION_REQUEST_TIMEOUT_MS = 10_000;
const LOCATION_CACHE_MAX_AGE_MS = 60_000;

/** 获取浏览器定位；输入：无；输出：经纬度或明确失败状态；调用方：数字人授权题卡提交。 */
function requestBrowserLocation(): Promise<UserLocationContext> {
  if (!navigator.geolocation) return Promise.resolve({ status: "unavailable" });

  return new Promise((resolve) => {
    try {
      navigator.geolocation.getCurrentPosition(
        ({ coords }) =>
          resolve({
            status: "granted",
            latitude: coords.latitude,
            longitude: coords.longitude,
            accuracy_meters: coords.accuracy,
          }),
        (error) =>
          resolve({ status: error.code === error.PERMISSION_DENIED ? "denied" : "unavailable" }),
        {
          enableHighAccuracy: true,
          timeout: LOCATION_REQUEST_TIMEOUT_MS,
          maximumAge: LOCATION_CACHE_MAX_AGE_MS,
        },
      );
    } catch {
      resolve({ status: "unavailable" });
    }
  });
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

function ImageResult({ part }: { part: ImageResultContentPart }) {
  const [hasError, setHasError] = useState(false);
  if (hasError) {
    return (
      <p className="conversation-image-result__status" role="status">
        {t("生成图片暂时无法显示。")}
      </p>
    );
  }
  return (
    <figure className="conversation-image-result">
      <a
        aria-label={t("查看生成图片原图")}
        href={part.image_url}
        rel="noopener noreferrer"
        target="_blank"
      >
        <img
          alt={t("图片助手生成的商品图片")}
          onError={() => setHasError(true)}
          src={part.image_url}
        />
      </a>
    </figure>
  );
}

function getQuestionPart(message: ConversationMessage | undefined): QuestionContentPart | null {
  if (message?.role !== "assistant") return null;

  return (
    message.content.parts.find((part): part is QuestionContentPart => part.type === "question") ??
    null
  );
}

function getQuestionAnswersPart(
  message: ConversationMessage | undefined,
): QuestionAnswersContentPart | null {
  if (message?.role !== "user") return null;
  return (
    message.content.parts.find(
      (part): part is QuestionAnswersContentPart => part.type === "question_answers",
    ) ?? null
  );
}

function getQuestionAnswerItems(
  message: ConversationMessage | undefined,
  questionPart?: QuestionContentPart | null,
): SubmittedQuestionAnswer[] | null {
  const answersPart = getQuestionAnswersPart(message);
  if (!answersPart || answersPart.items.length === 0) return null;

  const answerByQuestionId = new Map(
    answersPart.items.map((item) => [item.question_id, item.answer]),
  );
  if (answerByQuestionId.size !== answersPart.items.length) return null;

  if (questionPart) {
    if (answersPart.items.length !== questionPart.questions.length) return null;

    const items = questionPart.questions.map((question) => {
      const answer = answerByQuestionId.get(question.id);
      return answer ? { question_id: question.id, question: question.title, answer } : null;
    });
    return items.every((item): item is SubmittedQuestionAnswer => item !== null) ? items : null;
  }

  return answersPart.items.every((item) => item.question && item.answer) ? answersPart.items : null;
}

function isLegacySubmittedAnswersMessage(message: ConversationMessage | undefined): boolean {
  if (message?.role !== "user") return false;
  const text = messageText(message);
  return text.startsWith("用户已提交以下选择：") || text.startsWith("已提交选择：");
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

/** 对话页面；负责消息、题卡交互及数字人明确授权后的浏览器定位。 */
export function ConversationPage({
  conversationId,
  embedded = false,
  panelOpen = true,
  onCollapsePanel,
  onConversationIdChange,
  onResumeSaved,
  onNavigate,
}: ConversationPageProps) {
  const { showToast } = useToast();
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [skillCode, setSkillCode] = useState(embedded ? "resume_assistant" : "general_chat");
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
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
  const [activeRun, setActiveRun] = useState<{ conversationId: string; runId: string } | null>(
    null,
  );
  const [pendingText, setPendingText] = useState<string | null>(null);
  const [streamedOutput, setStreamedOutput] = useState<{
    conversationId: string | null;
    text: string;
    status: "streaming" | "completed" | "interrupted" | "failed";
  } | null>(null);
  const [errorState, setErrorState] = useState<{
    conversationId: string | null;
    message: string;
  } | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const [showEmbeddedHistory, setShowEmbeddedHistory] = useState(false);
  const [isCreatingConversation, setIsCreatingConversation] = useState(false);
  const activeStreamControllerRef = useRef<AbortController | null>(null);
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
  const currentStreamedOutput =
    streamedOutput &&
    (streamedOutput.conversationId === conversationId || (!conversationId && pendingText !== null))
      ? streamedOutput
      : null;
  const displayedImageResultIds = new Set<string>();

  const refreshMessages = useCallback(
    async (activeConversationId: string): Promise<MessageListResponse> => {
      const history = await listAllMessages(activeConversationId);
      setMessages(history.items);
      setSkillCode(history.skill_code);
      setLoadedConversationId(activeConversationId);
      return history;
    },
    [],
  );

  useEffect(() => {
    return () => activeStreamControllerRef.current?.abort();
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId) return;

    let isActive = true;
    void listAllMessages(conversationId)
      .then((history) => {
        if (isActive) {
          setMessages(history.items);
          setSkillCode(history.skill_code);
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

  const followRun = useCallback(
    async (targetConversationId: string, runId: string, signal: AbortSignal) => {
      setActiveRun({ conversationId: targetConversationId, runId });
      await listenConversationRun(
        targetConversationId,
        runId,
        (content) =>
          setStreamedOutput((current) => ({
            conversationId: targetConversationId,
            text: (current?.conversationId === targetConversationId ? current.text : "") + content,
            status: "streaming",
          })),
        (questionMessage) =>
          setMessages((current) =>
            current.some((message) => message.id === questionMessage.id)
              ? current
              : [...current, questionMessage],
          ),
        (status) => {
          if (status === "completed" || status === "interrupted") {
            setIsSubmitting(false);
            setActiveRun((current) => (current?.runId === runId ? null : current));
            setStreamedOutput((current) =>
              current?.conversationId === targetConversationId ? { ...current, status } : current,
            );
            void refreshMessages(targetConversationId).then(() => {
              setStreamedOutput((current) =>
                current?.conversationId === targetConversationId ? null : current,
              );
              setHistoryRefreshKey((current) => current + 1);
            });
          } else if (status === "failed") {
            setIsSubmitting(false);
            setActiveRun((current) => (current?.runId === runId ? null : current));
            setStreamedOutput((current) =>
              current?.conversationId === targetConversationId
                ? { ...current, status: "failed" }
                : current,
            );
          }
        },
        signal,
      );
    },
    [refreshMessages],
  );

  useEffect(() => {
    if (!conversationId) return;
    let isCurrent = true;
    void getActiveConversationRun(conversationId)
      .then((active) => {
        if (!isCurrent || !active) return;
        const controller = new AbortController();
        activeStreamControllerRef.current = controller;
        setStreamedOutput({ conversationId, text: "", status: "streaming" });
        setIsSubmitting(true);
        void followRun(conversationId, active.run_id, controller.signal)
          .catch((error: unknown) => {
            if (!controller.signal.aborted) showToast("error", getConversationErrorMessage(error));
          })
          .finally(() => {
            if (activeStreamControllerRef.current === controller) {
              activeStreamControllerRef.current = null;
              setIsSubmitting(false);
            }
          });
      })
      .catch((error: unknown) => {
        if (isCurrent) showToast("error", getConversationErrorMessage(error));
      });
    return () => {
      isCurrent = false;
    };
  }, [conversationId, followRun, showToast]);

  useLayoutEffect(() => {
    if ((embedded && !panelOpen) || showEmbeddedHistory) return;
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
  }, [
    conversationId,
    currentStreamedOutput?.text,
    embedded,
    panelOpen,
    showEmbeddedHistory,
    isSubmitting,
    loadedConversationId,
    pendingText,
    visibleMessages,
  ]);

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

  async function handleCreateConversation() {
    if (isCreatingConversation) return;
    setIsCreatingConversation(true);
    setErrorState(null);
    try {
      const conversation = await createConversation("resume_assistant");
      setConversationTitle(conversation.title?.trim() || t("新对话"));
      setShowEmbeddedHistory(false);
      setQuestionStep({ messageId: null, index: 0 });
      setHistoryRefreshKey((current) => current + 1);
      onConversationIdChange?.(conversation.id);
    } catch (requestError) {
      showToast("error", getConversationErrorMessage(requestError));
    } finally {
      setIsCreatingConversation(false);
    }
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
    const controller = new AbortController();
    activeStreamControllerRef.current = controller;
    setIsSubmitting(true);
    setPendingText(text);
    setStreamedOutput({ conversationId, text: "", status: "streaming" });
    setErrorState(null);
    let activeConversationId = conversationId;
    let createdThisTurn = false;
    let streamCompleted = false;

    try {
      if (!activeConversationId) {
        const conversation = await createConversation(embedded ? "resume_assistant" : undefined);
        activeConversationId = conversation.id;
        createdThisTurn = true;
        setConversationTitle(conversation.title?.trim() || t("新对话"));
        setStreamedOutput({
          conversationId: activeConversationId,
          text: "",
          status: "streaming",
        });
      }

      const requestConversationId = activeConversationId;
      const run = await startConversationMessageRun(requestConversationId, text);
      setActiveRun({ conversationId: requestConversationId, runId: run.run_id });
      if (createdThisTurn) {
        if (embedded) onConversationIdChange?.(requestConversationId);
        else onNavigate(`${platformPaths.chat}/${requestConversationId}`);
      }
      await followRun(requestConversationId, run.run_id, controller.signal);
      streamCompleted = true;
      if (embedded) void refreshConversationTitle(activeConversationId);
      setDraft("");
    } catch (requestError) {
      if (controller.signal.aborted) return;
      setStreamedOutput((current) =>
        current ? { ...current, status: streamCompleted ? "completed" : "failed" } : current,
      );
      showToast("error", getConversationErrorMessage(requestError));
      if (activeConversationId) {
        try {
          await refreshMessages(activeConversationId);
        } catch {
          // 保留原始提交错误；稍后可通过重新加载按钮恢复消息。
        }
        setHistoryRefreshKey((current) => current + 1);
        if (createdThisTurn) {
          if (embedded) onConversationIdChange?.(activeConversationId);
          else onNavigate(`${platformPaths.chat}/${activeConversationId}`);
        }
      }
    } finally {
      if (activeStreamControllerRef.current === controller) {
        activeStreamControllerRef.current = null;
        setPendingText(null);
        setIsSubmitting(false);
      }
    }
  }

  async function handleSubmitAnswers() {
    if (!conversationId || !pendingQuestion || !canSubmitAnswers || isSubmitting) return;

    const confirmsResumeSave =
      skillCode === "resume_assistant" &&
      pendingQuestion.part.questions.some(
        (question) =>
          question.id === "resume_optimization" &&
          selectedAnswers[question.id] === "确认采用并保存",
      );
    const locationAnswer = selectedAnswers[DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID];
    // 以题目 ID 识别定位授权，避免页面 skillCode 尚未同步时跳过浏览器定位。
    const isLocationConsentQuestion = pendingQuestion.part.questions.some(
      (question) => question.id === DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID,
    );

    const controller = new AbortController();
    activeStreamControllerRef.current = controller;
    setIsSubmitting(true);
    setStreamedOutput({ conversationId, text: "", status: "streaming" });
    setErrorState(null);
    let streamCompleted = false;
    try {
      // 先由用户提交授权题卡，再在同一交互中调用浏览器定位 API，以便显示原生权限提示。
      const location =
        isLocationConsentQuestion && locationAnswer === DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER
          ? await requestBrowserLocation()
          : undefined;
      const run = await startQuestionAnswersRun(conversationId, selectedAnswers, location);
      setActiveRun({ conversationId, runId: run.run_id });
      await followRun(conversationId, run.run_id, controller.signal);
      streamCompleted = true;
      const updatedHistory = await listAllMessages(conversationId);
      setAnswerSelection({ conversationId, answers: {} });
      setQuestionStep({ messageId: null, index: 0 });
      setHistoryRefreshKey((current) => current + 1);
      if (confirmsResumeSave && resumeSaveSucceeded(updatedHistory)) {
        await onResumeSaved?.();
      }
    } catch (requestError) {
      if (controller.signal.aborted) {
        return;
      }
      setStreamedOutput((current) =>
        current ? { ...current, status: streamCompleted ? "completed" : "failed" } : current,
      );
      showToast("error", getConversationErrorMessage(requestError));
      try {
        await refreshMessages(conversationId);
      } catch {
        // 保留原始提交错误，避免错误提示被刷新失败覆盖。
      }
    } finally {
      if (activeStreamControllerRef.current === controller) {
        activeStreamControllerRef.current = null;
        setIsSubmitting(false);
      }
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

  async function handleInterrupt() {
    if (!activeRun || activeRun.conversationId !== conversationId) return;
    try {
      await interruptConversationRun(activeRun.conversationId, activeRun.runId);
    } catch (requestError) {
      showToast("error", getConversationErrorMessage(requestError));
    }
  }

  function handleMessagesScroll() {
    const log = messageLogRef.current;
    if (!log) return;

    const distanceFromBottom = log.scrollHeight - log.scrollTop - log.clientHeight;
    shouldFollowMessagesRef.current = distanceFromBottom <= 96;
  }

  function handleSelectEmbeddedConversation(id: string, title: string) {
    setConversationTitle(title);
    setShowEmbeddedHistory(false);
    onConversationIdChange?.(id);
  }

  async function refreshConversationTitle(activeConversationId: string) {
    try {
      const latest = await listConversations(0);
      const summary = latest.items.find((item) => item.id === activeConversationId);
      if (summary) setConversationTitle(summary.title?.trim() || t("未命名会话"));
    } catch {
      // 标题加载失败时保留当前会话名称，不影响消息功能。
    }
  }

  const agentName =
    skillCode === "image_agent"
      ? t("图片助手")
      : skillCode === "resume_assistant"
        ? t("简历助手")
        : t("对话助手");

  return (
    <div className={`conversation-page${embedded ? " conversation-page--embedded" : ""}`}>
      {!embedded && (
        <aside aria-label={t("历史会话导航")} className="conversation-page__history">
          <button
            className="button button--outline conversation-page__new"
            onClick={() => onNavigate(platformPaths.chat)}
            type="button"
          >
            <span aria-hidden="true">+</span>
            {t("新建对话")}
          </button>
          <ConversationHistory
            key={historyRefreshKey}
            onSelect={(id) => onNavigate(`${platformPaths.chat}/${id}`)}
            selectedId={conversationId}
            variant="sidebar"
          />
        </aside>
      )}

      <section aria-label={agentName} className="conversation-panel">
        <header className="conversation-panel__header">
          <div className="conversation-panel__identity">
            <h1>{embedded ? t("简历助手") : agentName}</h1>
            {embedded && conversationId && (
              <span title={conversationTitle ?? undefined}>
                {conversationTitle || t("未命名会话")}
              </span>
            )}
          </div>
          {embedded ? (
            <div className="conversation-panel__actions">
              <button
                aria-pressed={showEmbeddedHistory}
                className="resume-chat-icon-button"
                disabled={isCreatingConversation}
                onClick={() => setShowEmbeddedHistory((current) => !current)}
                type="button"
              >
                <PlatformIcon name="history" size={17} />
                <span>{t("历史")}</span>
              </button>
              <button
                className="resume-chat-icon-button"
                disabled={isCreatingConversation}
                onClick={() => void handleCreateConversation()}
                type="button"
              >
                <PlatformIcon name="plus" size={17} />
                <span>{t("新对话")}</span>
              </button>
              <button
                aria-label={t("收起简历助手")}
                className="resume-chat-icon-button resume-chat-icon-button--collapse"
                onClick={onCollapsePanel}
                type="button"
              >
                <PlatformIcon name="chevron" size={17} />
              </button>
            </div>
          ) : null}
        </header>

        {embedded && showEmbeddedHistory ? (
          <div className="conversation-panel__history">
            <ConversationHistory
              key={`resume-history-${historyRefreshKey}`}
              onSelect={handleSelectEmbeddedConversation}
              selectedId={conversationId}
              skillCode="resume_assistant"
              variant="embedded"
            />
          </div>
        ) : (
          <>
            <div
              aria-label={t("对话消息")}
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
                  <h1>{agentName}</h1>
                  <p>
                    {skillCode === "image_agent"
                      ? t("描述商品和画面效果，开始生成图片。")
                      : skillCode === "resume_assistant"
                        ? t("可以请我分析简历、讨论求职方向或优化内容。")
                        : t("有什么问题，尽管问我。")}
                  </p>
                  {embedded && (
                    <div aria-label={t("快捷提问")} className="conversation-empty__suggestions">
                      {RESUME_ASSISTANT_PROMPTS.map(({ label, prompt }) => (
                        <button
                          className="conversation-empty__suggestion"
                          key={label}
                          onClick={() => {
                            setDraft(t(prompt));
                            window.requestAnimationFrame(() => composerInputRef.current?.focus());
                          }}
                          type="button"
                        >
                          {t(label)}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {isLoading && (
                <p className="conversation-status" role="status">
                  {t("正在加载对话…")}
                </p>
              )}

              {!isLoading && !error && conversationId && visibleMessages.length === 0 && (
                <p className="conversation-status">{t("发送第一条消息，开始这段对话。")}</p>
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
                      {t("重新加载消息")}
                    </button>
                  )}
                </div>
              )}

              {!isLoading && error && visibleMessages.length === 0 && conversationId && (
                <p className="conversation-status">{t("暂时无法显示此会话内容。")}</p>
              )}

              {visibleMessages.map((message, index) => {
                const questionPart = getQuestionPart(message);
                const isCurrentQuestion = pendingQuestion?.messageId === message.id;
                const text = messageText(message);
                const imageResults = message.content.parts.filter(
                  (part): part is ImageResultContentPart => {
                    if (part.type !== "image_result") return false;
                    // 旧会话可能已经把同一图片写进多条消息，只展示首次生成记录。
                    if (displayedImageResultIds.has(part.task_result_id)) return false;
                    displayedImageResultIds.add(part.task_result_id);
                    return true;
                  },
                );
                const previousQuestionPart = getQuestionPart(visibleMessages[index - 1]);
                const questionAnswerItems =
                  message.role === "user"
                    ? getQuestionAnswerItems(message, previousQuestionPart)
                    : null;
                const nextMessage = visibleMessages[index + 1];
                const hasSubmittedQuestionAnswers =
                  questionPart !== null &&
                  nextMessage?.role === "user" &&
                  (getQuestionAnswersPart(nextMessage) !== null ||
                    isLegacySubmittedAnswersMessage(nextMessage));

                return (
                  <article
                    className={`conversation-message conversation-message--${message.role}${questionAnswerItems ? " conversation-message--question-answers" : ""}`}
                    key={message.id}
                  >
                    {/* 助手的一条消息共用一个气泡，文字和图片按内容顺序展示。 */}
                    {message.role === "assistant" && (text || imageResults.length > 0) && (
                      <div className="conversation-message__bubble">
                        {text && (
                          <div className="conversation-message__markdown">
                            <ReactMarkdown
                              components={markdownComponents}
                              remarkPlugins={[remarkGfm]}
                            >
                              {text}
                            </ReactMarkdown>
                          </div>
                        )}
                        {imageResults.map((part) => (
                          <ImageResult key={part.task_result_id} part={part} />
                        ))}
                      </div>
                    )}
                    {message.role === "user" &&
                      text &&
                      (questionAnswerItems ? (
                        <QuestionAnswerCard items={questionAnswerItems} />
                      ) : (
                        <p className="conversation-message__text">{text}</p>
                      ))}
                    {questionPart && isCurrentQuestion && (
                      <QuestionWizard
                        currentIndex={currentQuestionIndex}
                        isSubmitting={isSubmitting}
                        messageId={message.id}
                        onNext={() =>
                          setQuestionStep({
                            messageId: message.id,
                            index: currentQuestionIndex + 1,
                          })
                        }
                        onPrevious={() =>
                          setQuestionStep({
                            messageId: message.id,
                            index: currentQuestionIndex - 1,
                          })
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
                    {questionPart &&
                      !isCurrentQuestion &&
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

              {pendingText && (
                <article
                  aria-label={t("正在发送的消息")}
                  className="conversation-message conversation-message--user conversation-message--pending"
                >
                  <p className="conversation-message__text">{pendingText}</p>
                </article>
              )}

              {currentStreamedOutput?.text && (
                <article
                  aria-label={
                    currentStreamedOutput.status === "failed"
                      ? t("未完成的助手回答")
                      : t("助手回答")
                  }
                  className={`conversation-message conversation-message--assistant${
                    currentStreamedOutput.status === "streaming"
                      ? " conversation-message--streaming"
                      : ""
                  }`}
                >
                  <div className="conversation-message__bubble">
                    <div className="conversation-message__markdown">
                      <ReactMarkdown components={markdownComponents} remarkPlugins={[remarkGfm]}>
                        {currentStreamedOutput.text}
                      </ReactMarkdown>
                    </div>
                  </div>
                  {currentStreamedOutput.status === "failed" && (
                    <p className="conversation-stream-status" role="status">
                      {t("回答未完成，刷新后不会保留这部分内容。")}
                    </p>
                  )}
                </article>
              )}

              {isSubmitting && (
                <p className="conversation-status" role="status">
                  {t("助手正在生成…")}
                </p>
              )}
            </div>

            <form className="conversation-composer" onSubmit={(event) => void handleSend(event)}>
              <label className="conversation-visually-hidden" htmlFor="conversation-message-input">
                {t("发送消息")}
              </label>
              <textarea
                id="conversation-message-input"
                ref={composerInputRef}
                disabled={isLoading || Boolean(pendingQuestion)}
                maxLength={20_000}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder={
                  pendingQuestion
                    ? t("请先完成题卡选择。")
                    : t("输入消息，Enter 发送，Shift + Enter 换行")
                }
                value={draft}
              />
              <div className="conversation-composer__footer">
                {error && <span>{t("检查消息状态后再决定是否重试。")}</span>}
                <button
                  aria-label={isSubmitting ? t("中断回复") : t("发送消息")}
                  className="button button--primary conversation-composer__send"
                  disabled={
                    isSubmitting
                      ? !activeRun
                      : !draft.trim() || isLoading || Boolean(pendingQuestion)
                  }
                  onClick={
                    isSubmitting
                      ? (event) => {
                          event.preventDefault();
                          void handleInterrupt();
                        }
                      : undefined
                  }
                  ref={composerSendButtonRef}
                  type={isSubmitting ? "button" : "submit"}
                >
                  {isSubmitting ? (
                    <PlatformIcon name="close" size={16} />
                  ) : (
                    <PlatformIcon name="arrow" size={16} />
                  )}
                  {isSubmitting ? t("中断") : t("发送")}
                </button>
              </div>
            </form>
          </>
        )}
      </section>
    </div>
  );
}

function resumeSaveSucceeded(history: MessageListResponse): boolean {
  const finalAssistantMessage = [...history.items]
    .reverse()
    .find((message) => message.role === "assistant");
  return finalAssistantMessage
    ? messageText(finalAssistantMessage).trim() === "已按你的确认保存优化内容。"
    : false;
}
