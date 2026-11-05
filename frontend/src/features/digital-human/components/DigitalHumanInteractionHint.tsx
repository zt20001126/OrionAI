import { memo, useEffect, useState } from "react";

import { t } from "../../../i18n/localeStore";
import "./digitalHumanInteractionHint.css";

interface DigitalHumanInteractionHintProps {
  intervalMs?: number;
  durationMs?: number;
  enabled?: boolean;
}

const DEFAULT_INTERVAL_MS = 15_000;
const DEFAULT_DURATION_MS = 3_000;

/** 周期性提示数字人的鼠标交互方式，不参与画布事件处理。 */
export const DigitalHumanInteractionHint = memo(function DigitalHumanInteractionHint({
  intervalMs = DEFAULT_INTERVAL_MS,
  durationMs = DEFAULT_DURATION_MS,
  enabled = true,
}: DigitalHumanInteractionHintProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (!enabled) return;

    let hideTimeout: number | null = null;
    const interval = window.setInterval(() => {
      setIsVisible(true);
      if (hideTimeout !== null) window.clearTimeout(hideTimeout);
      hideTimeout = window.setTimeout(() => {
        setIsVisible(false);
        hideTimeout = null;
      }, durationMs);
    }, intervalMs);

    return () => {
      window.clearInterval(interval);
      if (hideTimeout !== null) window.clearTimeout(hideTimeout);
    };
  }, [durationMs, enabled, intervalMs]);

  if (!enabled || !isVisible) return null;

  return (
    <aside
      aria-label={t("数字人互动方式")}
      className="digital-human-interaction-hint"
      role="status"
      style={{ animationDuration: `${durationMs}ms` }}
    >
      <h2 className="digital-human-interaction-hint__title">{t("✨ 试试和我互动吧")}</h2>
      <ol className="digital-human-interaction-hint__list">
        <li className="digital-human-interaction-hint__item">
          <MouseClickIcon />
          <span className="digital-human-interaction-hint__copy">
            <strong>{t("单击头部")}</strong>
            <span>{t("我会歪头回应你～")}</span>
          </span>
        </li>
        <li className="digital-human-interaction-hint__item">
          <MouseClickIcon />
          <span className="digital-human-interaction-hint__copy">
            <strong>{t("单击身体")}</strong>
            <span>{t("我会挥手打招呼～")}</span>
          </span>
        </li>
        <li className="digital-human-interaction-hint__item">
          <MouseClickIcon doubleClick />
          <span className="digital-human-interaction-hint__copy">
            <strong>{t("双击身体")}</strong>
            <span>{t("我会开心地回应你～")}</span>
          </span>
        </li>
      </ol>
    </aside>
  );
});

function MouseClickIcon({ doubleClick = false }: { doubleClick?: boolean }) {
  return (
    <span aria-hidden="true" className="digital-human-interaction-hint__icon">
      <svg fill="none" viewBox="0 0 44 44">
        <path
          d="M22 5.5a10.5 10.5 0 0 0-10.5 10.5v12a10.5 10.5 0 0 0 21 0V16A10.5 10.5 0 0 0 22 5.5Z"
          stroke="currentColor"
          strokeWidth="2"
        />
        <path d="M22 6v12m-9.5 0h19" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
        <path d="M33 7v5m-2.5-2.5h5" stroke="#ef8bb8" strokeLinecap="round" strokeWidth="2" />
        {doubleClick ? (
          <text fill="currentColor" fontSize="10" fontWeight="700" x="29" y="36">
            ×2
          </text>
        ) : (
          <path d="M34 23v8m-4-4h8" stroke="#8a7cf5" strokeLinecap="round" strokeWidth="2" />
        )}
      </svg>
    </span>
  );
}
