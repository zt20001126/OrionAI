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
      <div aria-hidden="true" className="digital-human-composer__waves">
        <svg viewBox="0 0 800 32" preserveAspectRatio="none">
          <path
            className="digital-human-composer__wave digital-human-composer__wave--one"
            d="M-800 25 C-750 25 -750 12 -700 12 S-650 25 -600 25 S-550 18 -500 18 S-450 25 -400 25 C-350 25 -350 12 -300 12 S-250 25 -200 25 S-150 18 -100 18 S-50 25 0 25 C50 25 50 12 100 12 S150 25 200 25 S250 18 300 18 S350 25 400 25 C450 25 450 12 500 12 S550 25 600 25 S650 18 700 18 S750 25 800 25 C850 25 850 12 900 12 S950 25 1000 25 S1050 18 1100 18 S1150 25 1200 25"
          />
          <path
            className="digital-human-composer__wave digital-human-composer__wave--two"
            d="M-800 25 C-750 25 -750 20 -700 20 S-650 25 -600 25 S-550 14 -500 14 S-450 25 -400 25 C-350 25 -350 20 -300 20 S-250 25 -200 25 S-150 14 -100 14 S-50 25 0 25 C50 25 50 20 100 20 S150 25 200 25 S250 14 300 14 S350 25 400 25 C450 25 450 20 500 20 S550 25 600 25 S650 14 700 14 S750 25 800 25 C850 25 850 20 900 20 S950 25 1000 25 S1050 14 1100 14 S1150 25 1200 25"
          />
        </svg>
      </div>
      <label className="digital-human-visually-hidden" htmlFor="digital-human-message-input">
        {t("发送消息")}
      </label>
      <div className="digital-human-composer__input">
        <textarea
          id="digital-human-message-input"
          disabled={disabled}
          maxLength={20_000}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={handleKeyDown}
          ref={textareaRef}
          rows={1}
          placeholder={isRecording ? "" : undefined}
          value={draft}
        />
        {isRecording && (
          <span className="digital-human-composer__listening" role="status">
            {draft && <span>{t("正在聆听...")}</span>}
            <span aria-hidden="true" className="digital-human-composer__bars">
              {Array.from({ length: 7 }, (_, index) => (
                <i key={index} />
              ))}
            </span>
            {!draft && <span className="digital-human-visually-hidden">{t("正在聆听...")}</span>}
          </span>
        )}
      </div>
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
