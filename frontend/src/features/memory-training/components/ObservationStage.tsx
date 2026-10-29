interface ObservationStageProps {
  imageUrl: string;
  remainingMs: number;
  observationSeconds: number;
}

/** 以完整图片为中心展示由服务端截止时间校准的观察倒计时。 */
export function ObservationStage({
  imageUrl,
  remainingMs,
  observationSeconds,
}: ObservationStageProps) {
  const remainingSeconds = Math.ceil(remainingMs / 1000);
  const progress = Math.min(100, Math.max(0, (remainingMs / (observationSeconds * 1000)) * 100));

  return (
    <section className="memory-training__observation" aria-label="图片观察阶段">
      <div className="memory-training__observation-heading">
        <p>请仔细观察图片中的物体、颜色与位置关系</p>
        <span aria-label={`剩余 ${remainingSeconds} 秒`} className="memory-training__countdown">
          {remainingSeconds}
          <small>秒</small>
        </span>
      </div>
      <div
        aria-label={`观察时间剩余 ${remainingSeconds} 秒`}
        aria-valuemax={observationSeconds}
        aria-valuemin={0}
        aria-valuenow={remainingSeconds}
        className="memory-training__progress"
        role="progressbar"
      >
        <span style={{ width: `${progress}%` }} />
      </div>
      <div className="memory-training__image-frame">
        <img alt="记忆训练观察图片" src={imageUrl} />
      </div>
    </section>
  );
}
