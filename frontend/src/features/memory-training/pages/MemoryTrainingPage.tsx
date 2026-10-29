import { ObservationStage } from "../components/ObservationStage";
import { QuestionStage } from "../components/QuestionStage";
import { QuestionWaitingState } from "../components/QuestionWaitingState";
import { TrainingPreparation } from "../components/TrainingPreparation";
import { TrainingResult } from "../components/TrainingResult";
import { useMemoryTrainingSession } from "../hooks/useMemoryTrainingSession";
import type { PlatformRoute } from "../../platform/platformData";
import "../memory-training.css";

interface MemoryTrainingPageProps {
  onNavigate: (path: PlatformRoute, replace?: boolean) => Promise<void> | void;
}

/** 记忆训练页面容器，根据服务端阶段切换准备、观察、答题和结果视图。 */
export function MemoryTrainingPage({ onNavigate }: MemoryTrainingPageProps) {
  const training = useMemoryTrainingSession();
  const { session } = training;

  if (session.phase === "loading") {
    return (
      <main className="memory-training memory-training__loading" role="status">
        <span className="memory-training__spinner" aria-hidden="true" />
        <p>正在恢复训练状态…</p>
      </main>
    );
  }

  if (session.phase === "error") {
    return (
      <main className="memory-training memory-training__error-state">
        <h1>记忆训练暂不可用</h1>
        <p role="alert">{session.error}</p>
        <button className="button button--outline" onClick={() => void training.restore()} type="button">
          重试
        </button>
      </main>
    );
  }

  if (session.phase === "prepare" && session.preparation) {
    return (
      <main className="memory-training">
        <TrainingPreparation
          preparation={session.preparation}
          busy={session.busy}
          error={session.error}
          onStart={() => void training.startTraining()}
        />
      </main>
    );
  }

  if (session.phase === "image_loading") {
    return (
      <main className="memory-training memory-training__loading">
        <span className="memory-training__spinner" aria-hidden="true" />
        <p>正在加载训练图片</p>
        {session.error && <p className="memory-training__error" role="alert">{session.error}</p>}
        <button
          className="button button--outline"
          disabled={session.busy}
          onClick={() => void training.retryImageLoading()}
          type="button"
        >
          {session.busy ? "正在加载…" : "重试加载图片"}
        </button>
      </main>
    );
  }

  if (session.phase === "observing" && session.imageUrl && session.preparation) {
    return (
      <main className="memory-training">
        <ObservationStage
          imageUrl={session.imageUrl}
          remainingMs={session.remainingMs}
          observationSeconds={session.preparation.observation_seconds}
        />
      </main>
    );
  }

  if (session.phase === "waiting_questions") {
    return (
      <main className="memory-training memory-training__waiting-page">
        <QuestionWaitingState />
      </main>
    );
  }

  if (session.phase === "answering") {
    return (
      <main className="memory-training">
        <QuestionStage
          questions={session.questions}
          answers={session.answers}
          currentIndex={session.currentQuestionIndex}
          busy={session.busy}
          error={session.error}
          onChoose={training.chooseAnswer}
          onMove={training.moveToQuestion}
          onSubmit={() => void training.submitAnswers()}
        />
      </main>
    );
  }

  if (session.phase === "completed" && session.result) {
    return (
      <main className="memory-training memory-training--result">
        <TrainingResult
          result={session.result}
          onNavigate={onNavigate}
          onRetry={() => void training.startAgain()}
        />
      </main>
    );
  }

  return (
    <main className="memory-training memory-training__error-state">
      <h1>本次训练未能完成</h1>
      <p role="alert">{session.error ?? "题目准备失败，请重新开始训练。"}</p>
      <button className="button button--primary" onClick={() => void training.startAgain()} type="button">
        重新开始
      </button>
    </main>
  );
}
