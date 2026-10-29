import type { Preparation } from "../api/memoryTrainingApi";

interface TrainingPreparationProps {
  preparation: Preparation;
  busy: boolean;
  error: string | null;
  onStart: () => void;
}

/** 训练准备页说明固定规则，不包含训练图片。 */
export function TrainingPreparation({
  preparation,
  busy,
  error,
  onStart,
}: TrainingPreparationProps) {
  return (
    <section className="memory-training__preparation" aria-labelledby="memory-training-title">
      <div className="memory-training__intro">
        <h1 id="memory-training-title">{preparation.tool_name}</h1>
        <p>{preparation.description}</p>
      </div>

      <div className="memory-training__facts" aria-label="训练规则摘要">
        <div><strong>{preparation.observation_seconds} 秒</strong><span>观察时间</span></div>
        <div><strong>{preparation.question_count} 道题</strong><span>单选答题</span></div>
        <div><strong>{preparation.max_score} 分</strong><span>训练满分</span></div>
      </div>

      <div className="memory-training__rules">
        <h2>训练规则</h2>
        <ul>
          <li>图片加载完成后开始计时，请在 15 秒内仔细观察。</li>
          <li>观察结束后回答 5 道图片细节题，可以返回修改答案。</li>
          <li>每题 20 分，提交后查看本次图片、得分与答案解析。</li>
        </ul>
      </div>

      {error && <p className="memory-training__error" role="alert">{error}</p>}
      <button className="button button--primary" disabled={busy} onClick={onStart} type="button">
        {busy ? "正在准备图片…" : "开始观察"}
      </button>
    </section>
  );
}
