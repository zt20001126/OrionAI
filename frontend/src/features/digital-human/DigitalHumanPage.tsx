import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { t } from "../../i18n/localeStore";
import {
  DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER,
  DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID,
  createConversation,
  listAllMessages,
  planPlaceRoute,
  streamDigitalHumanReply,
  type DigitalHumanAudioEvent,
} from "../conversations/conversationApi";
import type {
  ConversationMessage,
  KlineChartPayload,
  MessageListResponse,
  PlaceCardsPayload,
  PlaceCard,
  QuestionContentPart,
  RouteMode,
} from "../conversations/conversationApi";
import { requestBrowserLocation } from "../conversations/browserLocation";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { DigitalHumanAvatarHost } from "./components/DigitalHumanAvatarHost";
import { DigitalHumanInteractionHint } from "./components/DigitalHumanInteractionHint";
import { DigitalHumanWelcome } from "./components/DigitalHumanWelcome";
import { DigitalHumanComposer } from "./components/DigitalHumanComposer";
import { DigitalHumanConversation } from "./components/DigitalHumanConversation";
import { DigitalHumanVoiceToggle } from "./components/DigitalHumanVoiceToggle";
import { VoiceRecordingOverlay } from "./components/VoiceRecordingOverlay";
import { DigitalHumanApiError } from "./digitalHumanApi";
import { useAssistantAudio } from "./hooks/useAssistantAudio";
import { useMicrophoneRecorder } from "./hooks/useMicrophoneRecorder";
import { createRequestKey } from "./requestKey";
import type { DigitalHumanStatus } from "./types";
import "./digitalHuman.css";

interface DigitalHumanPageProps {
  conversationId: string | null;
  onNavigate: (path: PlatformRoute) => void;
}

function getPendingQuestion(
  messages: ConversationMessage[],
): { messageId: string; part: QuestionContentPart } | null {
  const latestMessage = messages.at(-1);
  if (latestMessage?.role !== "assistant") return null;
  const questionPart = latestMessage.content.parts.find(
    (part): part is QuestionContentPart => part.type === "question",
  );
  return questionPart ? { messageId: latestMessage.id, part: questionPart } : null;
}

function formatQuestionAnswers(
  questionPart: QuestionContentPart,
  answers: Record<string, string>,
): string {
  return `用户已提交以下选择：\n${questionPart.questions
    .map((question) => `- ${question.title}：${answers[question.id]}`)
    .join("\n")}`;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

const VOICE_ENABLED_STORAGE_KEY = "orionai:digital-human:voice-enabled";
const ROUTE_MODE_BY_ANSWER: Record<string, RouteMode> = {
  步行: "walking",
  骑行: "cycling",
  驾车: "driving",
};

/** 建立商家路线方式题卡；输入商家名；输出可由共用题卡组件展示的问题；调用方：数字人路线入口。 */
function createRouteModeQuestion(placeName: string): QuestionContentPart["questions"] {
  return [
    {
      id: "merchant_route_mode",
      title: `选择前往${placeName}的路线方式`,
      type: "SingleChoice",
      options: [
        { label: "步行", description: "适合短距离出行" },
        { label: "骑行", description: "查看骑行路线和预计时间" },
        { label: "驾车", description: "查看驾车路线和预计时间" },
        { label: "暂不规划", description: "关闭路线选择" },
      ],
      allow_custom_input: false,
    },
  ];
}

/** 从本地偏好同步初始化播报状态；存储不可用时默认开启。 */
function readVoiceEnabledPreference(): boolean {
  try {
    return window.localStorage.getItem(VOICE_ENABLED_STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
}

/** 保存播报偏好；输入布尔状态；存储被浏览器禁用时静默降级。 */
function saveVoiceEnabledPreference(enabled: boolean): void {
  try {
    window.localStorage.setItem(VOICE_ENABLED_STORAGE_KEY, String(enabled));
  } catch {
    // 隐私模式或浏览器策略禁用存储时，当前页面状态仍可使用。
  }
}

/** 数字人交互页面：串联会话消息、语音识别、语音合成和数字人播放状态。 */
export function DigitalHumanPage({ conversationId, onNavigate }: DigitalHumanPageProps) {
  const { showToast } = useToast();
  const [showWelcome, setShowWelcome] = useState(true);
  const [voiceEnabled, setVoiceEnabled] = useState(readVoiceEnabledPreference);
  const [previousConversationId, setPreviousConversationId] = useState(conversationId);
  // 返回新会话时重新展示引导，打开历史会话则继续展示原消息。
  if (previousConversationId !== conversationId) {
    setPreviousConversationId(conversationId);
    if (conversationId === null) setShowWelcome(true);
  }
  const [loadedMessages, setLoadedMessages] = useState<{
    conversationId: string;
    items: ConversationMessage[];
  } | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [answerSelection, setAnswerSelection] = useState<{
    conversationId: string;
    messageId: string;
    answers: Record<string, string>;
  } | null>(null);
  const [questionStep, setQuestionStep] = useState<{
    conversationId: string | null;
    messageId: string | null;
    index: number;
  }>({ conversationId: null, messageId: null, index: 0 });
  const [streamedAssistantText, setStreamedAssistantText] = useState("");
  const [streamedKlineChart, setStreamedKlineChart] = useState<{
    conversationId: string;
    chart: KlineChartPayload;
  } | null>(null);
  const [streamedPlaceCards, setStreamedPlaceCards] = useState<{
    conversationId: string;
    cards: PlaceCardsPayload;
  } | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPlanningRoute, setIsPlanningRoute] = useState(false);
  const [routeModePrompt, setRouteModePrompt] = useState<{
    conversationId: string;
    messageId: string;
    place: PlaceCard;
    selectedAnswer: string;
  } | null>(null);
  const routeLockRef = useRef(false);
  const routeRequestRef = useRef<{
    conversationId: string;
    placeId: string;
    mode: RouteMode;
    key: string;
  } | null>(null);
  const audioTurnRef = useRef<string | null>(null);
  const nextSegmentRef = useRef(1);
  const requestStartedRef = useRef(0);
  const playbackEndedRef = useRef<number | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const submitLockRef = useRef(false);
  const conversationCreationLockRef = useRef(false);
  const activeConversationRef = useRef(conversationId);
  const preserveRequestForConversationRef = useRef<string | null>(null);
  const idempotencyRef = useRef<{ key: string; text: string } | null>(null);
  const assistantStreamRef = useRef("");
  const messages = useMemo(
    () =>
      conversationId && loadedMessages?.conversationId === conversationId
        ? loadedMessages.items
        : [],
    [conversationId, loadedMessages],
  );
  const pendingQuestion = useMemo(() => getPendingQuestion(messages), [messages]);
  const activeRouteModePrompt =
    routeModePrompt?.conversationId === conversationId ? routeModePrompt : null;
  const selectedAnswers =
    answerSelection?.conversationId === conversationId &&
    answerSelection.messageId === pendingQuestion?.messageId
      ? answerSelection.answers
      : {};
  const currentQuestionIndex =
    pendingQuestion &&
    questionStep.conversationId === conversationId &&
    questionStep.messageId === pendingQuestion.messageId
      ? Math.min(questionStep.index, pendingQuestion.part.questions.length - 1)
      : 0;
  const canSubmitAnswers =
    pendingQuestion !== null &&
    pendingQuestion.part.questions.every((question) => Boolean(selectedAnswers[question.id]));
  const isMessagesLoading = Boolean(
    conversationId && loadedMessages?.conversationId !== conversationId,
  );

  useLayoutEffect(() => {
    activeConversationRef.current = conversationId;
  }, [conversationId]);

  const onTranscribed = useCallback((text: string) => {
    setDraft(text);
  }, []);
  const onRecorderError = useCallback(
    (message: string) => showToast("error", message),
    [showToast],
  );
  const onAvatarLoadError = useCallback(
    (loadError: Error) =>
      showToast("error", errorMessage(loadError, t("数字人模型暂时无法加载。"))),
    [showToast],
  );
  const recorder = useMicrophoneRecorder({ onTranscribed, onError: onRecorderError });
  const { audioRef, isSpeaking, enqueueAudio, stopAudio } = useAssistantAudio();

  useEffect(() => {
    stopAudio();
  }, [conversationId, stopAudio]);

  useEffect(
    () => () => {
      requestRef.current?.abort();
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    assistantStreamRef.current = "";
    if (!conversationId) {
      return () => {
        cancelled = true;
      };
    }

    void listAllMessages(conversationId)
      .then((response) => {
        if (cancelled) return;
        if (response.skill_code !== "digital_human") {
          showToast("error", t("该会话不是数字人会话，无法在此打开。"));
          return;
        }
        setLoadedMessages({ conversationId, items: response.items });
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          showToast("error", errorMessage(loadError, t("数字人会话加载失败。")));
        }
      });

    return () => {
      cancelled = true;
      if (
        preserveRequestForConversationRef.current &&
        preserveRequestForConversationRef.current === activeConversationRef.current
      ) {
        preserveRequestForConversationRef.current = null;
      } else {
        requestRef.current?.abort();
      }
    };
  }, [conversationId, showToast]);

  const avatarStatus: DigitalHumanStatus = useMemo(() => {
    if (recorder.status === "starting" || recorder.status === "listening") return "listening";
    if (isSpeaking) return "speaking";
    if (recorder.status === "transcribing" || isSubmitting) return "thinking";
    return "idle";
  }, [isSpeaking, isSubmitting, recorder.status]);

  async function startNewConversation(preservePendingRequest = false): Promise<string | null> {
    if (conversationCreationLockRef.current) return null;
    conversationCreationLockRef.current = true;
    try {
      const conversation = await createConversation("digital_human");
      if (preservePendingRequest) {
        preserveRequestForConversationRef.current = conversation.id;
      }
      onNavigate(`${platformPaths.digitalHuman}/${conversation.id}`);
      return conversation.id;
    } finally {
      conversationCreationLockRef.current = false;
    }
  }

  async function refreshMessages(targetConversationId: string): Promise<MessageListResponse> {
    const response = await listAllMessages(targetConversationId);
    if (response.skill_code !== "digital_human") {
      throw new DigitalHumanApiError(t("该会话不是数字人会话，无法在此打开。"), 404);
    }
    setLoadedMessages({ conversationId: targetConversationId, items: response.items });
    return response;
  }

  /** 打开所选商家的路线方式题卡；路线仍绑定当前商家的 POI 坐标。 */
  function handlePlanRoute(place: PlaceCard) {
    if (!conversationId || routeLockRef.current || pendingQuestion) return;
    if (!place.location) {
      showToast("error", "商家缺少坐标，请重新搜索。");
      return;
    }
    setRouteModePrompt({
      conversationId,
      messageId: createRequestKey(),
      place,
      selectedAnswer: "",
    });
  }

  /** 获取授权位置并按题卡选择规划路线；结果写入当前会话后刷新消息。 */
  async function handleRouteModeSubmit() {
    if (!activeRouteModePrompt || routeLockRef.current) return;
    const mode = ROUTE_MODE_BY_ANSWER[activeRouteModePrompt.selectedAnswer];
    setRouteModePrompt(null);
    if (!mode) return;

    routeLockRef.current = true;
    setIsPlanningRoute(true);
    const target = activeRouteModePrompt.conversationId;
    const place = activeRouteModePrompt.place;
    try {
      const location = await requestBrowserLocation();
      if (location.status !== "granted")
        throw new Error(
          location.status === "denied"
            ? "定位权限被拒绝，请允许定位后重试。"
            : "无法获取当前位置，请检查定位后重试。",
        );
      const existing = routeRequestRef.current;
      const key =
        existing?.conversationId === target &&
        existing.placeId === place.id &&
        existing.mode === mode
          ? existing.key
          : createRequestKey();
      routeRequestRef.current = { conversationId: target, placeId: place.id, mode, key };
      await planPlaceRoute(target, place, location, mode, key);
      routeRequestRef.current = null;
      if (activeConversationRef.current === target) await refreshMessages(target);
    } catch (error) {
      if (activeConversationRef.current === target) {
        showToast("error", errorMessage(error, "路线规划失败，请重试。"));
        await refreshMessages(target).catch(() => undefined);
      }
    } finally {
      routeLockRef.current = false;
      setIsPlanningRoute(false);
    }
  }

  /** 将当前请求的音频段按顺序加入播放器；取消后忽略旧事件。 */
  function receiveAudio(event: DigitalHumanAudioEvent, signal: AbortSignal) {
    if (signal.aborted) return;
    if (!audioTurnRef.current) audioTurnRef.current = event.turn_id;
    if (event.turn_id !== audioTurnRef.current) return;
    if (event.type === "audio_error") {
      showToast("error", t("语音合成失败，文字回复已保留。"));
      return;
    }
    if (
      event.type !== "audio_segment" ||
      event.segment_id !== nextSegmentRef.current ||
      !event.audio
    )
      return;
    nextSegmentRef.current += 1;
    const bytes = Uint8Array.from(atob(event.audio), (char) => char.charCodeAt(0));
    return enqueueAudio(
      new Blob([bytes], { type: "audio/mpeg" }),
      () => showToast("error", t("语音播放失败，文字回复已保留。")),
      () => {
        const now = performance.now();
        console.info("digital_human_playback", {
          turn_id: event.turn_id,
          segment_id: event.segment_id,
          frontend_first_playback_ms:
            event.segment_id === 1 ? now - requestStartedRef.current : undefined,
          playback_gap_ms:
            playbackEndedRef.current === null ? undefined : now - playbackEndedRef.current,
        });
      },
      () => {
        playbackEndedRef.current = performance.now();
      },
    );
  }

  function stopReply() {
    requestRef.current?.abort();
    audioTurnRef.current = null;
    stopAudio();
  }

  /** 更新后续回复的播报偏好；当前已发送请求继续使用发送时的设置。 */
  function handleVoiceEnabledChange(enabled: boolean) {
    setVoiceEnabled(enabled);
    saveVoiceEnabledPreference(enabled);
  }

  /** 提交当前草稿并流式接收回复；发送后立即清空，失败时在原会话恢复草稿。 */
  async function handleSend() {
    const message = draft.trim();
    const voiceEnabledForTurn = voiceEnabled;
    if (
      !message ||
      submitLockRef.current ||
      isSubmitting ||
      pendingQuestion ||
      recorder.status !== "idle"
    ) {
      return;
    }
    setShowWelcome(false);
    stopReply();
    nextSegmentRef.current = 1;
    playbackEndedRef.current = null;
    requestStartedRef.current = performance.now();
    submitLockRef.current = true;
    setIsSubmitting(true);
    setPendingMessage(message);
    setDraft("");
    setStreamedAssistantText("");
    setStreamedKlineChart(null);
    setStreamedPlaceCards(null);
    assistantStreamRef.current = "";
    const controller = new AbortController();
    requestRef.current = controller;
    let activeConversationId = conversationId;
    try {
      const requestKey =
        idempotencyRef.current?.text === message ? idempotencyRef.current.key : createRequestKey();
      idempotencyRef.current = { key: requestKey, text: message };
      activeConversationId = activeConversationId ?? (await startNewConversation(true));
      if (!activeConversationId) return;
      const streamConversationId = activeConversationId;
      await streamDigitalHumanReply(
        activeConversationId,
        "messages",
        { message },
        (delta) => {
          assistantStreamRef.current += delta;
          setStreamedAssistantText(assistantStreamRef.current);
        },
        (event) => receiveAudio(event, controller.signal),
        controller.signal,
        requestKey,
        (chart) => setStreamedKlineChart({ conversationId: streamConversationId, chart }),
        voiceEnabledForTurn,
        (cards) => setStreamedPlaceCards({ conversationId: streamConversationId, cards }),
      );
      await refreshMessages(activeConversationId);
      // 持久化消息已加载，移除临时流式气泡，避免 TTS 期间重复展示同一回复。
      setStreamedAssistantText("");
      setStreamedKlineChart(null);
      setStreamedPlaceCards(null);
      assistantStreamRef.current = "";
      setIsSubmitting(false);
      setPendingMessage(null);
      idempotencyRef.current = null;
    } catch (sendError) {
      if (!controller.signal.aborted) {
        if (activeConversationRef.current === activeConversationId) {
          setDraft((current) => current || message);
        }
        showToast("error", errorMessage(sendError, t("发送消息失败，请稍后重试。")));
        if (activeConversationId) {
          void refreshMessages(activeConversationId).catch(() => undefined);
        }
      }
    } finally {
      submitLockRef.current = false;
      requestRef.current = null;
      setIsSubmitting(false);
      setPendingMessage(null);
      setStreamedAssistantText("");
      setStreamedKlineChart(null);
      setStreamedPlaceCards(null);
      assistantStreamRef.current = "";
    }
  }

  async function handleQuestionAnswerSubmit() {
    const voiceEnabledForTurn = voiceEnabled;
    if (
      !conversationId ||
      !pendingQuestion ||
      !canSubmitAnswers ||
      submitLockRef.current ||
      isSubmitting
    ) {
      return;
    }

    const targetConversationId = conversationId;
    const answers = selectedAnswers;
    const submittedText = formatQuestionAnswers(pendingQuestion.part, answers);
    stopReply();
    nextSegmentRef.current = 1;
    playbackEndedRef.current = null;
    requestStartedRef.current = performance.now();
    submitLockRef.current = true;
    setIsSubmitting(true);
    setPendingMessage(submittedText);
    setStreamedAssistantText("");
    setStreamedKlineChart(null);
    setStreamedPlaceCards(null);
    assistantStreamRef.current = "";
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      // 仅在用户提交位置授权题并明确同意时读取浏览器位置。
      const location =
        pendingQuestion.part.questions.some(
          (question) => question.id === DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID,
        ) &&
        answers[DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID] ===
          DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER
          ? await requestBrowserLocation()
          : undefined;
      if (controller.signal.aborted) return;
      await streamDigitalHumanReply(
        targetConversationId,
        "answers",
        { answers, ...(location ? { location } : {}) },
        (delta) => {
          assistantStreamRef.current += delta;
          setStreamedAssistantText(assistantStreamRef.current);
        },
        (event) => receiveAudio(event, controller.signal),
        controller.signal,
        undefined,
        (chart) => setStreamedKlineChart({ conversationId: targetConversationId, chart }),
        voiceEnabledForTurn,
        (cards) => setStreamedPlaceCards({ conversationId: targetConversationId, cards }),
      );
      await refreshMessages(targetConversationId);
      if (activeConversationRef.current !== targetConversationId) return;
      setAnswerSelection(null);
      setQuestionStep({ conversationId: null, messageId: null, index: 0 });
      setPendingMessage(null);
      setStreamedAssistantText("");
      setStreamedKlineChart(null);
      setStreamedPlaceCards(null);
      assistantStreamRef.current = "";
      setIsSubmitting(false);
    } catch (submitError) {
      if (!controller.signal.aborted) {
        showToast("error", errorMessage(submitError, t("提交答案失败，请稍后重试。")));
        void refreshMessages(targetConversationId).catch(() => undefined);
      }
    } finally {
      submitLockRef.current = false;
      if (requestRef.current === controller) requestRef.current = null;
      setIsSubmitting(false);
      setPendingMessage(null);
      setStreamedAssistantText("");
      setStreamedKlineChart(null);
      setStreamedPlaceCards(null);
      assistantStreamRef.current = "";
    }
  }

  function toggleRecording() {
    if (recorder.status === "listening") {
      recorder.stopRecording();
      return;
    }
    if (recorder.status !== "idle") return;
    void recorder.startRecording();
  }

  const isBusy =
    isSubmitting || isPlanningRoute || activeRouteModePrompt !== null || recorder.status !== "idle";

  return (
    <section aria-label={t("Orion 助手")} className="digital-human-page">
      <div className="digital-human-layout">
        <section aria-label={t("数字人展示区域")} className="digital-human-stage">
          <DigitalHumanVoiceToggle enabled={voiceEnabled} onChange={handleVoiceEnabledChange} />
          <DigitalHumanAvatarHost
            audioRef={audioRef}
            isSpeaking={isSpeaking}
            onLoadError={onAvatarLoadError}
            status={avatarStatus}
          />
          <DigitalHumanInteractionHint />
        </section>

        <section aria-label={t("数字人对话")} className="digital-human-chat">
          {showWelcome && !conversationId ? (
            <DigitalHumanWelcome
              draft={draft}
              onSelect={setDraft}
              onSkip={() => setShowWelcome(false)}
            />
          ) : (
            <DigitalHumanConversation
              onPlanRoute={(place) => void handlePlanRoute(place)}
              isPlanningRoute={isPlanningRoute || isSubmitting || pendingQuestion !== null}
              isSelectingRouteMode={activeRouteModePrompt !== null}
              routeModePrompt={
                activeRouteModePrompt
                  ? {
                      messageId: activeRouteModePrompt.messageId,
                      questions: createRouteModeQuestion(activeRouteModePrompt.place.name),
                      selectedAnswers: activeRouteModePrompt.selectedAnswer
                        ? { merchant_route_mode: activeRouteModePrompt.selectedAnswer }
                        : {},
                    }
                  : null
              }
              onRouteModeAnswerSelect={(answer) => {
                setRouteModePrompt((current) =>
                  current?.conversationId === conversationId
                    ? { ...current, selectedAnswer: answer }
                    : current,
                );
              }}
              onRouteModeSubmit={() => void handleRouteModeSubmit()}
              currentQuestionIndex={currentQuestionIndex}
              isSubmitting={isSubmitting}
              isLoading={isMessagesLoading}
              messages={messages}
              onQuestionAnswerSelect={(questionId, answer) => {
                if (!conversationId || !pendingQuestion) return;
                setAnswerSelection((current) => {
                  const currentAnswers =
                    current?.conversationId === conversationId &&
                    current.messageId === pendingQuestion.messageId
                      ? current.answers
                      : {};
                  return {
                    conversationId,
                    messageId: pendingQuestion.messageId,
                    answers: { ...currentAnswers, [questionId]: answer },
                  };
                });
              }}
              onQuestionNext={() => {
                if (!conversationId || !pendingQuestion) return;
                setQuestionStep({
                  conversationId,
                  messageId: pendingQuestion.messageId,
                  index: currentQuestionIndex + 1,
                });
              }}
              onQuestionPrevious={() => {
                if (!conversationId || !pendingQuestion) return;
                setQuestionStep({
                  conversationId,
                  messageId: pendingQuestion.messageId,
                  index: currentQuestionIndex - 1,
                });
              }}
              onQuestionSubmit={() => void handleQuestionAnswerSubmit()}
              pendingMessage={pendingMessage}
              pendingQuestionMessageId={pendingQuestion?.messageId ?? null}
              selectedAnswers={selectedAnswers}
              streamedAssistantText={streamedAssistantText}
              streamedPlaceCards={
                streamedPlaceCards?.conversationId === conversationId
                  ? streamedPlaceCards.cards
                  : null
              }
              streamedKlineChart={
                streamedKlineChart?.conversationId === conversationId
                  ? streamedKlineChart.chart
                  : null
              }
            />
          )}
          <DigitalHumanComposer
            disabled={isBusy || pendingQuestion !== null}
            isSubmitting={isSubmitting}
            onStop={stopReply}
            draft={draft}
            recorderStatus={recorder.status}
            onDraftChange={setDraft}
            onSend={() => void handleSend()}
            onToggleRecording={toggleRecording}
          />
        </section>
        <VoiceRecordingOverlay
          isRecording={recorder.status === "listening"}
          onCancel={recorder.cancelRecording}
        />
      </div>
      <audio aria-hidden="true" className="digital-human-audio" ref={audioRef} />
    </section>
  );
}
