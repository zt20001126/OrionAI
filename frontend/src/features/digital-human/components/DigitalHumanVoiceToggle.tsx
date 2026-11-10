import { PlatformIcon } from "../../platform/PlatformIcon";

interface DigitalHumanVoiceToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}

/** 切换数字人回复播报；输入当前状态，输出新状态；由数字人展示区域调用。 */
export function DigitalHumanVoiceToggle({ enabled, onChange }: DigitalHumanVoiceToggleProps) {
  return (
    <button
      aria-checked={enabled}
      aria-label={enabled ? "关闭语音播报" : "开启语音播报"}
      className={`digital-human-voice-toggle${enabled ? " is-enabled" : " is-muted"}`}
      onClick={() => onChange(!enabled)}
      role="switch"
      type="button"
    >
      <PlatformIcon name={enabled ? "speaker" : "speakerMuted"} size={19} />
      <span className="digital-human-voice-toggle__label">语音播报</span>
      <span aria-hidden="true" className="digital-human-voice-toggle__switch">
        <span className="digital-human-voice-toggle__switch-thumb" />
      </span>
    </button>
  );
}
