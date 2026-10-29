import { useEffect, useState } from "react";

import type { TrainingResult } from "../api/memoryTrainingApi";
import { platformPaths, type PlatformRoute } from "../../platform/platformData";

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
        <h1 id="memory-result-title">本次训练结果</h1>
        <button
          aria-label="放大查看本次训练图片"
          className="memory-training__result-image-button"
          onClick={() => setImageExpanded(true)}
          type="button"
        >
          <img alt="本次训练观察的原始图片" src={result.image_url} />
        </button>
        <p>点击图片可放大查看</p>
      </div>

      <div className="memory-training__result-details">
        <div className="memory-training__score-panel">
          <span>本次得分</span>
          <strong>{result.score}<small> / 100</small></strong>
          <div className="memory-training__score-stats">
            <span>答对 <b>{result.correct_count}</b> 题</span>
            <span>答错 <b>{result.incorrect_count}</b> 题</span>
            <span>正确率 <b>{Math.round(result.correct_rate * 100)}%</b></span>
          </div>
        </div>

        <div className="memory-training__review-list">
          <h2>答案解析</h2>
          {result.questions.map((question, index) => (
            <details className="memory-training__review-card" key={question.id}>
              <summary>
                <span>第 {index + 1} 题 · {question.is_correct ? "回答正确" : "回答错误"}</span>
                <strong>{question.score} 分</strong>
              </summary>
              <div className="memory-training__review-content">
                <h3>{question.prompt}</h3>
                <p>你的答案：{question.user_option_id}. {question.user_option_text}</p>
                <p>正确答案：{question.correct_option_id}. {question.correct_option_text}</p>
                <p className="memory-training__explanation">解析：{question.explanation}</p>
              </div>
            </details>
          ))}
        </div>

        <div className="memory-training__result-actions">
          <button className="button button--primary" onClick={onRetry} type="button">
            再来一次
          </button>
          <button
            className="button button--outline"
            onClick={() => void onNavigate(platformPaths.market)}
            type="button"
          >
            返回技能市场
          </button>
        </div>
      </div>

      {imageExpanded && (
        <div
          aria-label="训练图片预览"
          aria-modal="true"
          className="memory-training__lightbox"
          onClick={(event) => {
            if (event.target === event.currentTarget) setImageExpanded(false);
          }}
          role="dialog"
        >
          <button
            aria-label="关闭图片预览"
            className="memory-training__lightbox-close"
            onClick={() => setImageExpanded(false)}
            type="button"
          >
            关闭
          </button>
          <img alt="本次训练观察的原始图片放大预览" src={result.image_url} />
        </div>
      )}
    </section>
  );
}
