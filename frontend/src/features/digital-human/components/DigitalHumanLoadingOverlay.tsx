import { t } from "../../../i18n/localeStore";
import "./digitalHumanLoading.css";

interface Props {
  phase: "loading" | "initializing" | "ready" | "error";
  progress: number | null;
  onRetry: () => void;
  errorMessage?: string;
}

/** 展示数字人区域的加载、首帧准备和失败重试；由数字人渲染组件调用。 */
export function DigitalHumanLoadingOverlay({ phase, progress, onRetry, errorMessage }: Props) {
  const steps = ["加载模型", "初始化场景", "准备就绪"];
  const current = phase === "loading" ? 0 : phase === "ready" ? 2 : 1;
  return (
    <div
      className={`human-loading human-loading--${phase}`}
      aria-hidden={phase === "ready" || undefined}
    >
      {phase === "error" ? (
        <div className="human-loading__error" role="alert">
          <strong>{errorMessage ?? t("3D数字人暂时无法显示")}</strong>
          <button className="button button--primary" onClick={onRetry} type="button">
            {t("重新加载")}
          </button>
        </div>
      ) : (
        <div className="human-loading__content" role="status">
          <div className="human-loading__portrait" aria-hidden="true">
            <div className="human-loading__ring" />
            <svg viewBox="0 0 120 140" className="human-loading__silhouette">
              <path d="M60 12c-17 0-29 13-29 31 0 12 5 21 12 27v13c-4 5-13 7-20 11C12 100 9 110 7 130h106c-2-20-5-30-16-36-7-4-16-6-20-11V70c7-6 12-15 12-27C89 25 77 12 60 12Z" />
            </svg>
          </div>
          <strong className="human-loading__title">{t("正在加载数字人...")}</strong>
          <span className="human-loading__subtitle">{t("首次加载可能需要一些时间，请稍候")}</span>
          <div className="human-loading__progress-row">
            <div
              className="human-loading__track"
              role="progressbar"
              aria-label={t("数字人模型下载进度")}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={phase === "loading" && progress !== null ? progress : undefined}
            >
              <span
                className={
                  phase !== "loading" || progress === null ? "human-loading__indeterminate" : ""
                }
                style={
                  phase === "loading" && progress !== null ? { width: `${progress}%` } : undefined
                }
              />
            </div>
            {phase === "loading" && progress !== null && <span>{progress}%</span>}
          </div>
          <div className="human-loading__steps">
            {steps.map((step, index) => (
              <div
                className={`human-loading__step${index === current ? " is-current" : ""}${index < current ? " is-complete" : ""}`}
                key={step}
              >
                <span className="human-loading__step-icon" aria-hidden="true">
                  {index < current ? "✓" : index === 0 ? "◇" : index === 1 ? "☷" : "✧"}
                </span>
                <span>{t(step)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
