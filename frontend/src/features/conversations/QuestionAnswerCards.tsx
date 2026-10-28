import { useId, useState } from "react";

import { PlatformIcon } from "../platform/PlatformIcon";
import type { SingleChoiceQuestion, SubmittedQuestionAnswer } from "./conversationApi";

interface CompletedQuestionCardProps {
  questions: SingleChoiceQuestion[];
}

interface QuestionAnswerCardProps {
  items: SubmittedQuestionAnswer[];
}

export function CompletedQuestionCard({ questions }: CompletedQuestionCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const detailsId = useId();

  return (
    <section
      aria-label={`本轮答题已完成，共 ${questions.length} 题`}
      className="completed-question-card"
    >
      <button
        aria-controls={detailsId}
        aria-expanded={isExpanded}
        className="completed-question-card__toggle"
        onClick={() => setIsExpanded((expanded) => !expanded)}
        type="button"
      >
        <span aria-hidden="true" className="completed-question-card__status-icon">
          <svg viewBox="0 0 20 20" fill="none">
            <path d="m4.5 10.2 3.4 3.3 7.6-7.3" />
          </svg>
        </span>
        <span className="completed-question-card__heading">
          <strong>本轮答题已完成</strong>
          <span>共 {questions.length} 题</span>
        </span>
        <PlatformIcon name="chevron" size={18} />
      </button>

      <div
        aria-hidden={!isExpanded}
        className={`completed-question-card__details${isExpanded ? " is-expanded" : ""}`}
        id={detailsId}
      >
        <div className="completed-question-card__details-inner">
          <ol className="completed-question-card__list">
            {questions.map((question, index) => (
              <li className="completed-question-card__item" key={question.id}>
                <span className="completed-question-card__number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="completed-question-card__question">
                  <p>{question.title}</p>
                  {question.context && (
                    <p className="completed-question-card__context">{question.context}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

export function QuestionAnswerCard({ items }: QuestionAnswerCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const detailsId = useId();

  return (
    <section aria-label={`我的回答，共 ${items.length} 题`} className="question-answer-card">
      <button
        aria-controls={detailsId}
        aria-expanded={isExpanded}
        className="question-answer-card__toggle"
        onClick={() => setIsExpanded((expanded) => !expanded)}
        type="button"
      >
        <span aria-hidden="true" className="completed-question-card__status-icon">
          <svg viewBox="0 0 20 20" fill="none">
            <path d="m4.5 10.2 3.4 3.3 7.6-7.3" />
          </svg>
        </span>
        <span className="completed-question-card__heading">
          <strong>我的回答已提交</strong>
          <span>共 {items.length} 题</span>
        </span>
        <PlatformIcon name="chevron" size={18} />
      </button>

      <div
        aria-hidden={!isExpanded}
        className={`question-answer-card__details${isExpanded ? " is-expanded" : ""}`}
        id={detailsId}
      >
        <div className="question-answer-card__details-inner">
          <ol className="question-answer-card__list">
            {items.map((item, index) => (
              <li className="question-answer-card__item" key={item.question_id}>
                <div className="question-answer-card__question">
                  <span className="question-answer-card__number">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <p>{item.question}</p>
                </div>
                <p className="question-answer-card__answer">
                  <strong>我的选择：</strong>
                  <span>{item.answer}</span>
                </p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
