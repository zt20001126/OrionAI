import type { PublicQuestion } from "../api/memoryTrainingApi";

interface QuestionStageProps {
  questions: PublicQuestion[];
  answers: Record<string, string>;
  currentIndex: number;
  busy: boolean;
  error: string | null;
  onChoose: (questionId: string, optionId: string) => void;
  onMove: (index: number) => void;
  onSubmit: () => void;
}

/** 展示一道单选题，保留前后导航和最后一题提交操作。 */
export function QuestionStage({
  questions,
  answers,
  currentIndex,
  busy,
  error,
  onChoose,
  onMove,
  onSubmit,
}: QuestionStageProps) {
  const question = questions[currentIndex];
  if (!question) return null;
  const answeredCount = Object.keys(answers).length;
  const isLastQuestion = currentIndex === questions.length - 1;

  return (
    <section className="memory-training__question-stage" aria-labelledby="memory-question-title">
      <div className="memory-training__question-progress">
        <div>
          <span>第 {currentIndex + 1} / {questions.length} 题</span>
          <span>{answeredCount} 题已作答</span>
        </div>
        <div className="memory-training__progress" aria-hidden="true">
          <span style={{ width: `${((currentIndex + 1) / questions.length) * 100}%` }} />
        </div>
      </div>

      <div className="memory-training__question-card">
        <h1 id="memory-question-title">{question.prompt}</h1>
        <div className="memory-training__options" role="radiogroup" aria-label={question.prompt}>
          {question.options.map((option) => {
            const selected = answers[question.id] === option.id;
            return (
              <button
                aria-checked={selected}
                className={`memory-training__option${selected ? " is-selected" : ""}`}
                key={option.id}
                onClick={() => onChoose(question.id, option.id)}
                role="radio"
                type="button"
              >
                <span className="memory-training__option-id">{option.id}</span>
                <span>{option.text}</span>
              </button>
            );
          })}
        </div>
      </div>

      {error && <p className="memory-training__error" role="alert">{error}</p>}
      <div className="memory-training__question-actions">
        <button
          className="button button--outline"
          disabled={currentIndex === 0 || busy}
          onClick={() => onMove(currentIndex - 1)}
          type="button"
        >
          上一题
        </button>
        {isLastQuestion ? (
          <button
            className="button button--primary"
            disabled={answeredCount !== questions.length || busy}
            onClick={onSubmit}
            type="button"
          >
            {busy ? "正在评分…" : "提交答案"}
          </button>
        ) : (
          <button
            className="button button--primary"
            disabled={busy}
            onClick={() => onMove(currentIndex + 1)}
            type="button"
          >
            下一题
          </button>
        )}
      </div>
      {isLastQuestion && answeredCount !== questions.length && (
        <p className="memory-training__hint">请完成全部题目后再提交。</p>
      )}
    </section>
  );
}
