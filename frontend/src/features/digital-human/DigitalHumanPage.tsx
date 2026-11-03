import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { t } from "../../i18n/localeStore";
import {
  createConversation,
  listAllMessages,
  streamConversationMessage,
} from "../conversations/conversationApi";
import type { ConversationMessage, MessageListResponse } from "../conversations/conversationApi";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { DigitalHumanAvatar } from "./components/DigitalHumanAvatar";
import { DigitalHumanComposer } from "./components/DigitalHumanComposer";
import { DigitalHumanConversation } from "./components/DigitalHumanConversation";
import {
  DigitalHumanApiError,
  listDigitalHumanConversations,
  synthesizeSpeech,
} from "./digitalHumanApi";
import { useAssistantAudio } from "./hooks/useAssistantAudio";
import { useMicrophoneRecorder } from "./hooks/useMicrophoneRecorder";
import type { DigitalHumanConversationSummary, DigitalHumanStatus } from "./types";
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

export function DigitalHumanPage({ conversationId, onNavigate }: DigitalHumanPageProps) {
  const [history, setHistory] = useState<DigitalHumanConversationSummary[]>([]);
  const [historyTotalCount, setHistoryTotalCount] = useState(0);
  const [loadedMessages, setLoadedMessages] = useState<{
    conversationId: string;
    items: ConversationMessage[];
  } | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [streamedAssistantText, setStreamedAssistantText] = useState("");
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [isLoadingMoreHistory, setIsLoadingMoreHistory] = useState(false);
  const [isCreatingConversation, setIsCreatingConversation] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const [voiceResponse, setVoiceResponse] = useState<{
    conversationId: string;
    text: string;
    audio: Blob | null;
  } | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const voiceRequestRef = useRef<AbortController | null>(null);
  const submitLockRef = useRef(false);
  const voicePlaybackLockRef = useRef(false);
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

  const fetchHistory = useCallback((offset = 0) => listDigitalHumanConversations(offset, 50), []);
  const storeHistoryPage = useCallback(
    (response: Awaited<ReturnType<typeof listDigitalHumanConversations>>, append = false) => {
      setHistory((current) => (append ? [...current, ...response.items] : response.items));
      setHistoryTotalCount(response.total_count);
    },
    [],
  );
  const reportHistoryError = useCallback((loadError: unknown) => {
    setError(loadError instanceof Error ? loadError.message : t("数字人会话记录加载失败。"));
  }, []);
  const loadHistory = useCallback(
    async (offset = 0, append = false) => {
      try {
        storeHistoryPage(await fetchHistory(offset), append);
      } catch (loadError) {
        reportHistoryError(loadError);
      } finally {
        if (append) setIsLoadingMoreHistory(false);
        else setIsHistoryLoading(false);
      }
    },
    [fetchHistory, reportHistoryError, storeHistoryPage],
  );

  useEffect(() => {
    let cancelled = false;
    void fetchHistory()
      .then((response) => {
        if (!cancelled) storeHistoryPage(response);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) reportHistoryError(loadError);
      })
      .finally(() => {
        if (!cancelled) setIsHistoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fetchHistory, reportHistoryError, storeHistoryPage]);

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
          setError(t("该会话不是数字人会话，无法在此打开。"));
          return;
        }
        setLoadedMessages({ conversationId, items: response.items });
        setError(null);
      })
      .catch((loadError: unknown) => {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : t("数字人会话加载失败。"));
        }
      });
    return () => {
      cancelled = true;
      voiceRequestRef.current?.abort();
      voiceRequestRef.current = null;
      if (
        preserveRequestForConversationRef.current &&
        preserveRequestForConversationRef.current === activeConversationRef.current
      ) {
        preserveRequestForConversationRef.current = null;
      } else {
        requestRef.current?.abort();
      }
    };
  }, [conversationId]);

  const onTranscribed = useCallback((text: string) => {
    setDraft(text);
    setVoiceNotice(t("语音已转成文字，请检查后发送。"));
    setError(null);
  }, []);
  const recorder = useMicrophoneRecorder({ onTranscribed });
  const audio = useAssistantAudio();
  const { audioRef, isSpeaking, mouthOpen, playAudio, stopAudio } = audio;

  const loadMoreHistory = () => {
    if (!isLoadingMoreHistory && history.length < historyTotalCount) {
      setIsLoadingMoreHistory(true);
      void loadHistory(history.length, true);
    }
  };

  useEffect(() => {
    stopAudio();
  }, [conversationId, stopAudio]);

  const avatarStatus: DigitalHumanStatus = useMemo(() => {
    if (recorder.status === "starting" || recorder.status === "listening") return "listening";
    if (isSpeaking) return "speaking";
    if (recorder.status === "transcribing" || isSubmitting || isSynthesizing) return "thinking";
    return "idle";
  }, [isSpeaking, isSubmitting, isSynthesizing, recorder.status]);

  async function startNewConversation(preservePendingRequest = false): Promise<string | null> {
    if (conversationCreationLockRef.current) return null;
    conversationCreationLockRef.current = true;
    setIsCreatingConversation(true);
    try {
      const conversation = await createConversation("digital_human");
      if (preservePendingRequest) {
        preserveRequestForConversationRef.current = conversation.id;
      }
      onNavigate(`${platformPaths.digitalHuman}/${conversation.id}`);
      setIsHistoryLoading(true);
      await loadHistory();
      return conversation.id;
    } finally {
      conversationCreationLockRef.current = false;
      setIsCreatingConversation(false);
    }
  }

  async function refreshMessages(targetConversationId: string): Promise<MessageListResponse> {
    const response = await listAllMessages(targetConversationId);
    if (response.skill_code !== "digital_human") {
      throw new DigitalHumanApiError(t("该会话不是数字人会话，无法在此打开。"), 404);
    }
    setLoadedMessages({ conversationId: targetConversationId, items: response.items });
    void loadHistory();
    return response;
  }

  async function handleSend() {
    const message = draft.trim();
    if (!message || submitLockRef.current || isSubmitting || recorder.status !== "idle") return;
    submitLockRef.current = true;
    setError(null);
    setVoiceNotice(null);
    setVoiceResponse(null);
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
      setIsSubmitting(false);
      setDraft("");
      setPendingMessage(null);
      idempotencyRef.current = null;
      const answer = getAssistantText(persistedHistory);
      if (answer) {
        setVoiceResponse({ conversationId: activeConversationId, text: answer, audio: null });
        setIsSynthesizing(true);
        try {
          const audioBlob = await synthesizeSpeech(prepareSpeechText(answer), controller.signal);
          if (activeConversationRef.current !== activeConversationId) return;
          setVoiceResponse({
            conversationId: activeConversationId,
            text: answer,
            audio: audioBlob,
          });
          await playAudio(audioBlob);
        } catch {
          if (activeConversationRef.current === activeConversationId) {
            setVoiceNotice(t("文字回复已保存，可点击下方按钮重试语音。"));
          }
        } finally {
          setIsSynthesizing(false);
        }
      }
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : t("发送消息失败，请稍后重试。"));
      if (activeConversationId) {
        void refreshMessages(activeConversationId).catch(() => undefined);
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

  async function handleStartNew() {
    if (
      submitLockRef.current ||
      conversationCreationLockRef.current ||
      isBusy ||
      recorder.status !== "idle"
    ) {
      return;
    }
    try {
      setError(null);
      await startNewConversation();
      setDraft("");
      setPendingMessage(null);
      idempotencyRef.current = null;
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : t("无法创建数字人会话。"));
    }
  }

  function toggleRecording() {
    setError(null);
    if (recorder.status === "listening") {
      recorder.stopRecording();
      return;
    }
    if (recorder.status !== "idle") return;
    setVoiceNotice(null);
    void recorder.startRecording();
  }

  async function playAssistantResponse() {
    if (
      voicePlaybackLockRef.current ||
      !voiceResponse ||
      voiceResponse.conversationId !== conversationId
    ) {
      return;
    }
    voicePlaybackLockRef.current = true;
    setIsSynthesizing(true);
    setVoiceNotice(null);
    const controller = new AbortController();
    voiceRequestRef.current = controller;
    try {
      const audioBlob =
        voiceResponse.audio ??
        (await synthesizeSpeech(prepareSpeechText(voiceResponse.text), controller.signal));
      if (activeConversationRef.current !== voiceResponse.conversationId) return;
      if (!voiceResponse.audio) {
        setVoiceResponse({ ...voiceResponse, audio: audioBlob });
      }
      await playAudio(audioBlob);
    } catch {
      if (activeConversationRef.current === voiceResponse.conversationId) {
        setVoiceNotice(t("语音生成或播放失败，请重试。"));
      }
    } finally {
      if (voiceRequestRef.current === controller) voiceRequestRef.current = null;
      voicePlaybackLockRef.current = false;
      setIsSynthesizing(false);
    }
  }

  const isBusy = isSubmitting || isSynthesizing || recorder.status !== "idle";

  return (
    <section aria-labelledby="digital-human-title" className="digital-human-page">
      <header className="digital-human-page__header">
        <div>
          <h1 id="digital-human-title">{t("数字人助手")}</h1>
          <p>{t("通过文字或语音开始对话，回复文字会保存在会话记录中。")}</p>
        </div>
        <button
          className="button button--primary"
          disabled={isBusy || isCreatingConversation || recorder.status !== "idle"}
          onClick={() => void handleStartNew()}
          type="button"
        >
          {t("新建会话")}
        </button>
      </header>

      <div className="digital-human-layout">
        <aside aria-label={t("数字人和历史会话")} className="digital-human-sidebar">
          <DigitalHumanAvatar mouthOpen={mouthOpen} status={avatarStatus} />
          <section aria-labelledby="digital-human-history-title" className="digital-human-history">
            <h2 id="digital-human-history-title">{t("数字人会话")}</h2>
            {isHistoryLoading ? (
              <p className="digital-human-muted" role="status">
                {t("正在加载会话…")}
              </p>
            ) : history.length === 0 ? (
              <p className="digital-human-muted">{t("还没有数字人会话。")}</p>
            ) : (
              <ul>
                {history.map((item) => (
                  <li key={item.id}>
                    <button
                      aria-current={conversationId === item.id ? "page" : undefined}
                      className={conversationId === item.id ? "is-active" : ""}
                      onClick={() => onNavigate(`${platformPaths.digitalHuman}/${item.id}`)}
                      type="button"
                    >
                      <span>{item.title || t("未命名会话")}</span>
                      <time dateTime={item.updated_at}>
                        {new Date(item.updated_at).toLocaleDateString()}
                      </time>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {!isHistoryLoading && history.length < historyTotalCount && (
              <button
                className="button button--secondary"
                disabled={isLoadingMoreHistory}
                onClick={loadMoreHistory}
                type="button"
              >
                {isLoadingMoreHistory ? t("正在加载…") : t("加载更多会话")}
              </button>
            )}
          </section>
        </aside>

        <section aria-label={t("数字人对话")} className="digital-human-chat">
          {conversationId ? (
            <>
              <DigitalHumanConversation
                isLoading={isMessagesLoading}
                isThinking={
                  isSubmitting ||
                  recorder.status === "transcribing" ||
                  (isSynthesizing && !isSpeaking)
                }
                messages={messages}
                pendingMessage={pendingMessage}
                streamedAssistantText={streamedAssistantText}
              />
              <DigitalHumanComposer
                disabled={isBusy}
                draft={draft}
                isRecording={recorder.status === "listening"}
                onDraftChange={(value) => {
                  setDraft(value);
                  setVoiceNotice(null);
                }}
                onSend={() => void handleSend()}
                onToggleRecording={toggleRecording}
              />
            </>
          ) : (
            <div className="digital-human-empty">
              <h2>{t("开始和数字人对话")}</h2>
              <p>{t("新建一段会话，或从左侧打开已有记录。")}</p>
              <button
                className="button button--outline"
                disabled={isCreatingConversation}
                onClick={() => void handleStartNew()}
                type="button"
              >
                {t("新建数字人会话")}
              </button>
            </div>
          )}
          {(error || recorder.error || voiceNotice) && (
            <p
              className={error || recorder.error ? "digital-human-alert" : "digital-human-notice"}
              role={error || recorder.error ? "alert" : "status"}
            >
              {error || recorder.error || voiceNotice}
            </p>
          )}
          {voiceResponse?.conversationId === conversationId && (
            <button
              className="digital-human-play-voice button button--outline"
              disabled={isSynthesizing}
              onClick={() => void playAssistantResponse()}
              type="button"
            >
              {voiceResponse.audio ? t("播放回复语音") : t("重试生成语音")}
            </button>
          )}
          {recorder.error && (
            <button
              className="digital-human-play-voice button button--secondary"
              onClick={recorder.clearError}
              type="button"
            >
              {t("关闭提示")}
            </button>
          )}
        </section>
      </div>
      <audio aria-hidden="true" className="digital-human-audio" ref={audioRef} />
    </section>
  );
}
