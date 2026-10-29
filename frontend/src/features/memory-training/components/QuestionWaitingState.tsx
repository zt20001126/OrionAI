/** 展示图片隐藏后的题目生成等待状态。 */
export function QuestionWaitingState() {
  return (
    <section className="memory-training__waiting" aria-live="polite" role="status">
      <span className="memory-training__spinner" aria-hidden="true" />
      <h1>正在准备记忆测试</h1>
      <p>正在根据刚才的图片生成 5 道题目，请稍候。</p>
    </section>
  );
}
