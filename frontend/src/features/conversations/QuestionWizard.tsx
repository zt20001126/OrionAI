import type { QuestionContentPart } from "./conversationApi";
import { t } from "../../i18n/localeStore";
import "./question-cards.css";

export interface QuestionWizardProps {
  currentIndex: number;
  isSubmitting: boolean;
  messageId: string;
  onNext: () => void;
  onPrevious: () => void;
  onSelect: (questionId: string, answer: string) => void;
  onSubmit: () => void;
  questions: QuestionContentPart["questions"];
  selectedAnswers: Record<string, string>;
}

/** 展示单题、进度和答题操作；由通用对话与数字人会话共同使用。 */
export function QuestionWizard({
  currentIndex,
  isSubmitting,
  messageId,
  onNext,
  onPrevious,
  onSelect,
  onSubmit,
  questions,
  selectedAnswers,
}: QuestionWizardProps) {
  const question = questions[currentIndex];
  if (!question) return null;

  const hasSteps = questions.length > 1;
  const hasAnswer = Boolean(selectedAnswers[question.id]?.trim());
  const isLastQuestion = currentIndex === questions.length - 1;

  return (
    <section aria-label={t("问题答题卡")} className="question-card">
      <header className="question-card__header">
        <strong>{t("需要你的回答")}</strong>
        {hasSteps && (
          <span>
            {t("第")} {currentIndex + 1} / {questions.length} {t("题")}
          </span>
        )}
      </header>

      {hasSteps && (
        <div
          aria-label={t("答题进度")}
          aria-valuemax={questions.length}
          aria-valuemin={1}
          aria-valuenow={currentIndex + 1}
          className="question-card__progress"
          role="progressbar"
        >
          <span style={{ width: `${((currentIndex + 1) / questions.length) * 100}%` }} />
        </div>
      )}

      <fieldset className="question-card__question" disabled={isSubmitting}>
        <legend>{question.title}</legend>
        {"context" in question && question.context && (
          <div className="question-card__context-block">
            {question.id === "resume_optimization" && (
              <strong className="question-card__context-title">{t("修改候选预览")}</strong>
            )}
            <pre className="question-card__context">{question.context}</pre>
          </div>
        )}
        {question.type === "Text" ? (
          <input
            aria-label={question.title}
            className="form-input"
            maxLength={100}
            onChange={(event) => onSelect(question.id, event.target.value)}
            type="text"
            value={selectedAnswers[question.id] ?? ""}
          />
        ) : question.options.map((option) => (
          <label className="question-card__option" key={option.label}>
            <input
              checked={selectedAnswers[question.id] === option.label}
              name={`question-${messageId}-${question.id}`}
              onChange={() => onSelect(question.id, option.label)}
              type="radio"
              value={option.label}
            />
            <span>
              <strong>{option.label}</strong>
              <small>{option.description}</small>
            </span>
          </label>
        ))}
      </fieldset>

      <footer className="question-card__footer">
        {hasSteps && currentIndex > 0 ? (
          <button
            className="button button--outline"
            disabled={isSubmitting}
            onClick={onPrevious}
            type="button"
          >
            {t("← 上一题")}
          </button>
        ) : (
          <span />
        )}

        {isLastQuestion ? (
          <button
            className="button button--primary"
            disabled={isSubmitting || !questions.every((item) => selectedAnswers[item.id]?.trim())}
            onClick={onSubmit}
            type="button"
          >
            {isSubmitting ? t("正在提交…") : t("提交答案")}
          </button>
        ) : (
          <button
            className="button button--primary"
            disabled={isSubmitting || !hasAnswer}
            onClick={onNext}
            type="button"
          >
            {t("下一题 →")}
          </button>
        )}
      </footer>
    </section>
  );
}
