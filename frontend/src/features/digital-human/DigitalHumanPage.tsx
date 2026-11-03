import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { t } from "../../i18n/localeStore";
import {
  createConversation,
  listAllMessages,
  streamConversationMessage,
} from "../conversations/conversationApi";
import type { ConversationMessage, MessageListResponse } from "../conversations/conversationApi";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { DigitalHumanAvatarHost } from "./components/DigitalHumanAvatarHost";
import { DigitalHumanComposer } from "./components/DigitalHumanComposer";
import { DigitalHumanConversation } from "./components/DigitalHumanConversation";
import { DigitalHumanApiError, synthesizeSpeech } from "./digitalHumanApi";
import { useAssistantAudio } from "./hooks/useAssistantAudio";
import { useMicrophoneRecorder } from "./hooks/useMicrophoneRecorder";
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

function createRequestKey(): string {
  return crypto.randomUUID();
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
  const messages =
    conversationId && loadedMessages?.conversationId === conversationId ? loadedMessages.items : [];
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

  async function handleSend() {
    const message = draft.trim();
    if (!message || submitLockRef.current || isSubmitting || recorder.status !== "idle") return;
    submitLockRef.current = true;
    setIsSubmitting(true);
    setPendingMessage(message);
    setStreamedAssistantText("");
    assistantStreamRef.current = "";
    const controller = new AbortController();
    requestRef.current = controller;
    const requestKey =
      idempotencyRef.current?.text === message ? idempotencyRef.current.key : createRequestKey();
    idempotencyRef.current = { key: requestKey, text: message };
    let activeConversationId = conversationId;

    try {
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
      if (answer) {
        setIsSynthesizing(true);
        try {
          const audioBlob = await synthesizeSpeech(prepareSpeechText(answer), controller.signal);
          if (activeConversationRef.current !== activeConversationId) return;
          try {
            await playAudio(audioBlob);
          } catch {
            if (activeConversationRef.current === activeConversationId) {
              showToast("error", t("语音播放失败，文字回复已保留。"));
            }
          }
        } catch (speechError) {
          if (
            activeConversationRef.current === activeConversationId &&
            !controller.signal.aborted
          ) {
            showToast(
              "error",
              `${errorMessage(speechError, t("语音合成失败。"))} ${t("文字回复已保留。")}`,
            );
          }
        } finally {
          setIsSynthesizing(false);
        }
      }
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
        </section>

        <section aria-label={t("数字人对话")} className="digital-human-chat">
          <DigitalHumanConversation
            isLoading={isMessagesLoading}
            messages={messages}
            pendingMessage={pendingMessage}
            streamedAssistantText={streamedAssistantText}
          />
          <DigitalHumanComposer
            disabled={isBusy}
            draft={draft}
            isRecording={recorder.status === "listening"}
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
