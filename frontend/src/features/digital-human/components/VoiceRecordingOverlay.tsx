import { useEffect } from "react";

import { t } from "../../../i18n/localeStore";
import { PlatformIcon } from "../../platform/PlatformIcon";
import "./voiceRecordingOverlay.css";

interface VoiceRecordingOverlayProps {
  isRecording: boolean;
  onCancel: () => void;
}

/** 展示录音动画；输入：录音状态和取消回调；输出：悬浮交互界面；调用方：数字人页面。 */
export function VoiceRecordingOverlay({ isRecording, onCancel }: VoiceRecordingOverlayProps) {
  useEffect(() => {
    if (!isRecording) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isRecording, onCancel]);

  return (
    <div className={`voice-recording-overlay${isRecording ? " is-visible" : ""}`}>
      <button
        aria-label={t("取消录音")}
        className="voice-recording-overlay__cancel"
        disabled={!isRecording}
        onClick={onCancel}
        type="button"
      >
        <span className="voice-recording-overlay__visual" aria-hidden="true">
          {[0, 1, 2].map((index) => (
            <span className="voice-recording-overlay__ring" key={index} />
          ))}
          <span className="voice-recording-overlay__bars voice-recording-overlay__bars--left">
            {Array.from({ length: 6 }, (_, index) => (
              <i key={index} />
            ))}
          </span>
          <span className="voice-recording-overlay__mic">
            <PlatformIcon name="microphone" size={56} />
          </span>
          <span className="voice-recording-overlay__bars">
            {Array.from({ length: 6 }, (_, index) => (
              <i key={index} />
            ))}
          </span>
        </span>
        <span className="voice-recording-overlay__title">{t("正在聆听...")}</span>
        <span className="voice-recording-overlay__hint">{t("点击或按 Esc 取消")}</span>
      </button>
    </div>
  );
}
