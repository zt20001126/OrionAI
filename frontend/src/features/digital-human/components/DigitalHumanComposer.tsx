import { useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from "react";

import { PlatformIcon } from "../../platform/PlatformIcon";
import { t } from "../../../i18n/localeStore";
import type { RecorderStatus } from "../hooks/useMicrophoneRecorder";

interface DigitalHumanComposerProps {
  draft: string;
  disabled: boolean;
  isSubmitting?: boolean;
  onStop?: () => void;
  recorderStatus: RecorderStatus;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onToggleRecording: () => void;
}

/** 数字人会话输入区，提供文字输入、录音切换和消息发送。 */
export function DigitalHumanComposer({
  draft,
  disabled,
  isSubmitting = false,
  onStop,
  recorderStatus,
  onDraftChange,
  onSend,
  onToggleRecording,
}: DigitalHumanComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const restoreFocusRef = useRef(false);
  const wasDisabledRef = useRef(disabled);
  const isRecording = recorderStatus === "listening";
  const isProcessing = recorderStatus === "starting" || recorderStatus === "transcribing";
  const recordingButtonLabel =
    recorderStatus === "starting"
      ? t("正在准备录音…")
      : recorderStatus === "transcribing"
        ? t("正在识别语音…")
        : isRecording
          ? t("停止录音")
          : t("开始录音");

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
  }, [draft]);

  useLayoutEffect(() => {
    if (wasDisabledRef.current && !disabled && restoreFocusRef.current) {
      textareaRef.current?.focus();
      restoreFocusRef.current = false;
    }
    wasDisabledRef.current = disabled;
  }, [disabled]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (draft.trim() && !disabled) restoreFocusRef.current = true;
    onSend();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (draft.trim() && !disabled) restoreFocusRef.current = true;
      onSend();
    }
  }

  return (
    <form className="digital-human-composer" onSubmit={submit}>
      <label className="digital-human-visually-hidden" htmlFor="digital-human-message-input">
        {t("发送消息")}
      </label>
      <textarea
        id="digital-human-message-input"
        disabled={disabled}
        maxLength={20_000}
        onChange={(event) => onDraftChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={t("输入消息…")}
        ref={textareaRef}
        rows={1}
        value={draft}
      />
      <div className="digital-human-composer__actions">
        <button
          aria-label={recordingButtonLabel}
          aria-busy={isProcessing}
          title={recordingButtonLabel}
          aria-pressed={isRecording}
          className={`button button--outline digital-human-composer__button digital-human-composer__button--voice${isRecording ? " is-recording" : ""}${isProcessing ? " is-processing" : ""}`}
          disabled={disabled && !isRecording}
          onClick={onToggleRecording}
          type="button"
        >
          {isProcessing ? (
            <span aria-hidden="true" className="digital-human-composer__spinner" />
          ) : (
            <PlatformIcon name={isRecording ? "close" : "microphone"} size={18} />
          )}
        </button>
        {isSubmitting ? (
          <button
            aria-label={t("停止生成")}
            className="button button--primary digital-human-composer__button digital-human-composer__button--send"
            onClick={onStop}
            type="button"
          >
            <PlatformIcon name="close" size={18} />
          </button>
        ) : (
          <button
            aria-label={t("发送")}
            title={t("发送")}
            className="button button--primary digital-human-composer__button digital-human-composer__button--send"
            disabled={!draft.trim() || disabled}
            type="submit"
          >
            <PlatformIcon name="arrow" size={18} />
          </button>
        )}
      </div>
    </form>
  );
}
