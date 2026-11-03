import { t } from "../../../i18n/localeStore";
import type { DigitalHumanStatus } from "../types";

interface DigitalHumanAvatarProps {
  status: DigitalHumanStatus;
  mouthOpen: number;
}

const STATUS_LABELS: Record<DigitalHumanStatus, string> = {
  idle: "待机中",
  listening: "正在聆听",
  thinking: "正在思考",
  speaking: "正在说话",
};

/** 独立的轻量 2D 数字人渲染器，后续可替换为 Live2D / 3D Adapter。 */
export function DigitalHumanAvatar({ status, mouthOpen }: DigitalHumanAvatarProps) {
  const mouthHeight = 2 + Math.min(1, Math.max(0, mouthOpen)) * 12;

  return (
    <section
      aria-label={t("数字人状态：{status}", { status: t(STATUS_LABELS[status]) })}
      className={`digital-human-avatar digital-human-avatar--${status}`}
      role="img"
    >
      <svg aria-hidden="true" className="digital-human-avatar__portrait" viewBox="0 0 220 240">
        <path
          className="digital-human-avatar__hair"
          d="M48 103c0-48 27-75 64-75s64 27 64 75v32H48z"
        />
        <ellipse className="digital-human-avatar__face" cx="110" cy="119" rx="57" ry="70" />
        <path
          className="digital-human-avatar__hairline"
          d="M56 103c8-41 27-61 56-61s48 20 56 61c-16-15-32-22-49-22-25 0-42 9-63 22z"
        />
        <ellipse className="digital-human-avatar__eye" cx="88" cy="116" rx="4" ry="5" />
        <ellipse className="digital-human-avatar__eye" cx="132" cy="116" rx="4" ry="5" />
        <ellipse
          className="digital-human-avatar__mouth"
          cx="110"
          cy="151"
          rx={8 + mouthOpen * 2}
          ry={mouthHeight}
        />
        <path
          className="digital-human-avatar__shoulders"
          d="M31 237c7-46 35-68 79-68s72 22 79 68z"
        />
        <path className="digital-human-avatar__shirt" d="m83 177 27 23 27-23 12 60H71z" />
      </svg>
      <span aria-live="polite" className="digital-human-avatar__status" role="status">
        {t(STATUS_LABELS[status])}
      </span>
    </section>
  );
}
