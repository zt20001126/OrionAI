import { useEffect, useState } from "react";

import type { TrainingResult } from "../api/memoryTrainingApi";
import { platformPaths, type PlatformRoute } from "../../platform/platformData";
import { t } from "../../../i18n/localeStore";

interface TrainingResultProps {
  result: TrainingResult;
  onNavigate: (path: PlatformRoute) => Promise<void> | void;
  onRetry: () => void;
}

/** 展示成绩和五题答案解析，并提供本次图片放大查看。 */
export function TrainingResult({ result, onNavigate, onRetry }: TrainingResultProps) {
  const [imageExpanded, setImageExpanded] = useState(false);

  useEffect(() => {
    if (!imageExpanded) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setImageExpanded(false);
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [imageExpanded]);

  return (
    <section className="memory-training__result-layout" aria-labelledby="memory-result-title">
      <div className="memory-training__result-image-column">
        <h1 id="memory-result-title">{t("本次训练结果")}</h1>
        <button
          aria-label={t("放大查看本次训练图片")}
          className="memory-training__result-image-button"
          onClick={() => setImageExpanded(true)}
          type="button"
        >
          <img alt={t("本次训练观察的原始图片")} src={result.image_url} />
        </button>
        <p>{t("点击图片可放大查看")}</p>
      </div>

      <div className="memory-training__result-details">
        <div className="memory-training__score-panel">
          <span>{t("本次得分")}</span>
          <strong>{result.score}<small> / 100</small></strong>
          <div className="memory-training__score-stats">
            <span>{t("答对")} <b>{result.correct_count}</b> {t("题")}</span>
            <span>{t("答错")} <b>{result.incorrect_count}</b> {t("题")}</span>
            <span>{t("正确率")} <b>{Math.round(result.correct_rate * 100)}%</b></span>
          </div>
        </div>

        <div className="memory-training__review-list">
          <h2>{t("答案解析")}</h2>
          {result.questions.map((question, index) => (
            <details className="memory-training__review-card" key={question.id}>
              <summary>
                <span>{t("第")} {index + 1} {t("题 ·")} {question.is_correct ? t("回答正确") : t("回答错误")}</span>
                <strong>{question.score} {t("分")}</strong>
              </summary>
              <div className="memory-training__review-content">
                <h3>{question.prompt}</h3>
                <p>{t("你的答案：")}{question.user_option_id}. {question.user_option_text}</p>
                <p>{t("正确答案：")}{question.correct_option_id}. {question.correct_option_text}</p>
                <p className="memory-training__explanation">{t("解析：")}{question.explanation}</p>
              </div>
            </details>
          ))}
        </div>

        <div className="memory-training__result-actions">
          <button className="button button--primary" onClick={onRetry} type="button">
            {t("再来一次")}
          </button>
          <button
            className="button button--outline"
            onClick={() => void onNavigate(platformPaths.market)}
            type="button"
          >
            {t("返回技能市场")}
          </button>
        </div>
      </div>

      {imageExpanded && (
        <div
          aria-label={t("训练图片预览")}
          aria-modal="true"
          className="memory-training__lightbox"
          onClick={(event) => {
            if (event.target === event.currentTarget) setImageExpanded(false);
          }}
          role="dialog"
        >
          <button
            aria-label={t("关闭图片预览")}
            className="memory-training__lightbox-close"
            onClick={() => setImageExpanded(false)}
            type="button"
          >
            {t("关闭")}
          </button>
          <img alt={t("本次训练观察的原始图片放大预览")} src={result.image_url} />
        </div>
      )}
    </section>
  );
}
