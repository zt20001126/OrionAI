import { useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from "react";

import { PlatformIcon } from "../../platform/PlatformIcon";
import { t } from "../../../i18n/localeStore";

interface DigitalHumanComposerProps {
  draft: string;
  disabled: boolean;
  isRecording: boolean;
  onDraftChange: (value: string) => void;
  onSend: () => void;
  onToggleRecording: () => void;
}

/** 数字人会话输入区，提供文字输入、录音切换和消息发送。 */
export function DigitalHumanComposer({
  draft,
  disabled,
  isRecording,
  onDraftChange,
  onSend,
  onToggleRecording,
}: DigitalHumanComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
  }, [draft]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSend();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
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
          aria-label={isRecording ? t("停止录音") : t("开始录音")}
          aria-pressed={isRecording}
          className="button button--outline digital-human-composer__button"
          disabled={disabled && !isRecording}
          onClick={onToggleRecording}
          type="button"
        >
          <PlatformIcon name={isRecording ? "close" : "microphone"} size={16} />
        </button>
        <button
          aria-label={t("发送")}
          className="button button--primary digital-human-composer__button"
          disabled={!draft.trim() || disabled}
          type="submit"
        >
          <PlatformIcon name="arrow" size={16} />
        </button>
      </div>
    </form>
  );
}
