import { t } from "../../../i18n/localeStore";
import type { SingleChoiceQuestion } from "../../conversations/conversationApi";

interface DigitalHumanQuestionCardProps {
  isPending: boolean;
  isSubmitting: boolean;
  messageId: string;
  onSelect: (questionId: string, answer: string) => void;
  onSubmit: () => void;
  questions: SingleChoiceQuestion[];
  selectedAnswers: Record<string, string>;
}

/** 显示数字人提出的选择题，并在当前待答题卡上提交答案。 */
export function DigitalHumanQuestionCard({
  isPending,
  isSubmitting,
  messageId,
  onSelect,
  onSubmit,
  questions,
  selectedAnswers,
}: DigitalHumanQuestionCardProps) {
  const canSubmit = questions.every((question) => Boolean(selectedAnswers[question.id]));

  return (
    <section aria-label={t("问题答题卡")} className="digital-human-question-card">
      <header className="digital-human-question-card__header">
        <strong>{isPending ? t("需要你的选择") : t("选择题")}</strong>
        {!isPending && <span>{t("已提交")}</span>}
      </header>
      {questions.map((question, index) => (
        <fieldset
          className="digital-human-question-card__question"
          disabled={!isPending || isSubmitting}
          key={question.id}
        >
          <legend>
            {questions.length > 1 ? `${index + 1}. ` : ""}
            {question.title}
          </legend>
          {question.context && (
            <p className="digital-human-question-card__context">{question.context}</p>
          )}
          {question.options.map((option) => (
            <label className="digital-human-question-card__option" key={option.label}>
              <input
                checked={selectedAnswers[question.id] === option.label}
                name={`digital-human-question-${messageId}-${question.id}`}
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
      ))}
      {isPending && (
        <footer className="digital-human-question-card__footer">
          <button
            className="button button--primary"
            disabled={isSubmitting || !canSubmit}
            onClick={onSubmit}
            type="button"
          >
            {isSubmitting ? t("正在提交…") : t("提交答案")}
          </button>
        </footer>
      )}
    </section>
  );
}
