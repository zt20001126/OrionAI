import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { t } from "../../i18n/localeStore";
import {
  createConversation,
  listAllMessages,
  streamConversationMessage,
  streamQuestionAnswers,
} from "../conversations/conversationApi";
import type {
  ConversationMessage,
  MessageListResponse,
  QuestionContentPart,
} from "../conversations/conversationApi";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { DigitalHumanAvatarHost } from "./components/DigitalHumanAvatarHost";
import { DigitalHumanInteractionHint } from "./components/DigitalHumanInteractionHint";
import { DigitalHumanComposer } from "./components/DigitalHumanComposer";
import { DigitalHumanConversation } from "./components/DigitalHumanConversation";
import { DigitalHumanApiError, synthesizeSpeech } from "./digitalHumanApi";
import { useAssistantAudio } from "./hooks/useAssistantAudio";
import { useMicrophoneRecorder } from "./hooks/useMicrophoneRecorder";
import { createRequestKey } from "./requestKey";
import type { DigitalHumanStatus } from "./types";
import "./digitalHuman.css";

interface DigitalHumanPageProps {
  conversationId: string | null;
  onNavigate: (path: PlatformRoute) => void;
}

function messageText(message: ConversationMessage): string {
  return message.content.parts
    .filter(
      (part): part is Extract<(typeof message.content.parts)[number], { type: "text" }> =>
        part.type === "text",
    )
    .map((part) => part.text)
    .join("\n")
    .trim();
}

function getAssistantText(history: MessageListResponse): string {
  const finalAssistant = [...history.items]
    .reverse()
    .find((message) => message.role === "assistant");
  return finalAssistant ? messageText(finalAssistant) : "";
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

function prepareSpeechText(text: string): string {
  return text
    .replace(/```[\w-]*\s*\n?/g, " ")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*(?:[-*+]|\d+[.)])\s+/gm, "")
    .replace(/[*_~`]/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** 数字人交互页面：串联会话消息、语音识别、语音合成和数字人播放状态。 */
export function DigitalHumanPage({ conversationId, onNavigate }: DigitalHumanPageProps) {
  const { showToast } = useToast();
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
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSynthesizing, setIsSynthesizing] = useState(false);
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
  const { audioRef, isSpeaking, playAudio, stopAudio } = useAssistantAudio();

  useEffect(() => {
    stopAudio();
  }, [conversationId, stopAudio]);

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
    if (recorder.status === "transcribing" || isSubmitting || isSynthesizing) return "thinking";
    return "idle";
  }, [isSpeaking, isSubmitting, isSynthesizing, recorder.status]);

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

  async function speakAssistantAnswer(
    answer: string,
    targetConversationId: string,
    signal: AbortSignal,
  ) {
    if (!answer || activeConversationRef.current !== targetConversationId) return;
    setIsSynthesizing(true);
    try {
      const audioBlob = await synthesizeSpeech(prepareSpeechText(answer), signal);
      if (activeConversationRef.current !== targetConversationId) return;
      try {
        await playAudio(audioBlob);
      } catch {
        if (activeConversationRef.current === targetConversationId) {
          showToast("error", t("语音播放失败，文字回复已保留。"));
        }
      }
    } catch (speechError) {
      if (activeConversationRef.current === targetConversationId && !signal.aborted) {
        showToast(
          "error",
          `${errorMessage(speechError, t("语音合成失败。"))} ${t("文字回复已保留。")}`,
        );
      }
    } finally {
      setIsSynthesizing(false);
    }
  }

  async function handleSend() {
    const message = draft.trim();
    if (
      !message ||
      submitLockRef.current ||
      isSubmitting ||
      pendingQuestion ||
      recorder.status !== "idle"
    ) {
      return;
    }
    submitLockRef.current = true;
    setIsSubmitting(true);
    setPendingMessage(message);
    setStreamedAssistantText("");
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
      await streamConversationMessage(
        activeConversationId,
        message,
        (delta) => {
          assistantStreamRef.current += delta;
          setStreamedAssistantText(assistantStreamRef.current);
        },
        controller.signal,
        requestKey,
      );
      const persistedHistory = await refreshMessages(activeConversationId);
      // 持久化消息已加载，移除临时流式气泡，避免 TTS 期间重复展示同一回复。
      setStreamedAssistantText("");
      assistantStreamRef.current = "";
      setIsSubmitting(false);
      setDraft("");
      setPendingMessage(null);
      idempotencyRef.current = null;
      const answer = getAssistantText(persistedHistory);
      await speakAssistantAnswer(answer, activeConversationId, controller.signal);
    } catch (sendError) {
      if (!controller.signal.aborted) {
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
      assistantStreamRef.current = "";
    }
  }

  async function handleQuestionAnswerSubmit() {
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
    submitLockRef.current = true;
    setIsSubmitting(true);
    setPendingMessage(submittedText);
    setStreamedAssistantText("");
    assistantStreamRef.current = "";
    const controller = new AbortController();
    requestRef.current = controller;

    try {
      await streamQuestionAnswers(
        targetConversationId,
        answers,
        (delta) => {
          assistantStreamRef.current += delta;
          setStreamedAssistantText(assistantStreamRef.current);
        },
        controller.signal,
      );
      const persistedHistory = await refreshMessages(targetConversationId);
      if (activeConversationRef.current !== targetConversationId) return;
      setAnswerSelection(null);
      setQuestionStep({ conversationId: null, messageId: null, index: 0 });
      setPendingMessage(null);
      setStreamedAssistantText("");
      assistantStreamRef.current = "";
      setIsSubmitting(false);
      await speakAssistantAnswer(
        getAssistantText(persistedHistory),
        targetConversationId,
        controller.signal,
      );
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

  const isBusy = isSubmitting || isSynthesizing || recorder.status !== "idle";

  return (
    <section aria-label={t("数字人助手")} className="digital-human-page">
      <div className="digital-human-layout">
        <section aria-label={t("数字人展示区域")} className="digital-human-stage">
          <DigitalHumanAvatarHost
            audioRef={audioRef}
            isSpeaking={isSpeaking}
            onLoadError={onAvatarLoadError}
            status={avatarStatus}
          />
          <DigitalHumanInteractionHint />
        </section>

        <section aria-label={t("数字人对话")} className="digital-human-chat">
          <DigitalHumanConversation
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
          />
          <DigitalHumanComposer
            disabled={isBusy || pendingQuestion !== null}
            draft={draft}
            recorderStatus={recorder.status}
            onDraftChange={setDraft}
            onSend={() => void handleSend()}
            onToggleRecording={toggleRecording}
          />
        </section>
      </div>
      <audio aria-hidden="true" className="digital-human-audio" ref={audioRef} />
    </section>
  );
}
