/** 在设置页和头像菜单弹窗中复用相同的问题反馈表单与提交逻辑。 */

import { useEffect, useRef, useState, type FormEvent } from "react";

import { useToast } from "../../components/ToastProvider";
import { PlatformIcon } from "../platform/PlatformIcon";
import { submitFeedback } from "./feedbackApi";
import { t } from "../../i18n/localeStore";

export type FeedbackFormVariant = "dialog" | "settings";

interface FeedbackFormProps {
  variant: FeedbackFormVariant;
  autoFocus?: boolean;
  onCancel?: () => void;
  onDirtyChange?: (isDirty: boolean) => void;
  onSubmittingChange?: (isSubmitting: boolean) => void;
  onSuccess?: () => void;
}

const TITLE_MAX_LENGTH = 100;
const CONTENT_MAX_LENGTH = 2000;

/** 反馈表单负责字段校验、字符计数、API 请求和统一成功/失败提示。 */
export function FeedbackForm({
  variant,
  autoFocus = false,
  onCancel,
  onDirtyChange,
  onSubmittingChange,
  onSuccess,
}: FeedbackFormProps) {
  const { showToast } = useToast();
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [errors, setErrors] = useState<{ title?: string; content?: string }>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isSubmittingRef = useRef(false);
  const isDirty = title.length > 0 || content.length > 0;
  const idPrefix = `feedback-${variant}`;

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  function resetForm() {
    setTitle("");
    setContent("");
    setErrors({});
    onDirtyChange?.(false);
  }

  function cancelForm() {
    if (isSubmittingRef.current) return;
    if (onCancel) {
      onCancel();
    } else {
      resetForm();
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmittingRef.current) return;

    const normalizedTitle = title.trim();
    const normalizedContent = content.trim();
    const nextErrors: { title?: string; content?: string } = {};
    if (!normalizedTitle) nextErrors.title = t("请输入反馈标题。");
    if (!normalizedContent) nextErrors.content = t("请输入反馈内容。");
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    isSubmittingRef.current = true;
    setIsSubmitting(true);
    onSubmittingChange?.(true);
    let didSubmit = false;
    try {
      await submitFeedback({ title: normalizedTitle, content: normalizedContent });
      resetForm();
      showToast("success", t("反馈提交成功，感谢你的支持！"));
      didSubmit = true;
    } catch {
      showToast("error", t("反馈提交失败，请稍后重试"));
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
      onSubmittingChange?.(false);
    }

    if (didSubmit) onSuccess?.();
  }

  return (
    <>
      <header
        className={`feedback-form__header${variant === "settings" ? " profile-settings__header" : ""}`}
      >
        {variant === "settings" ? (
          <h1 id={`${idPrefix}-title`}>{t("问题反馈")}</h1>
        ) : (
          <h2 id={`${idPrefix}-title`}>{t("问题反馈")}</h2>
        )}
        <p id={`${idPrefix}-description`}>{t("感谢你的反馈，这将帮助我们不断改进产品体验。")}</p>
      </header>

      <form
        className={`feedback-form feedback-form--${variant}`}
        noValidate
        onSubmit={handleSubmit}
      >
        <div className="feedback-form__field">
          <div className="feedback-form__field-heading">
            <label htmlFor={`${idPrefix}-subject`}>{t("标题")}</label>
            <span aria-live="polite">
              {title.length} / {TITLE_MAX_LENGTH}
            </span>
          </div>
          <input
            aria-describedby={errors.title ? `${idPrefix}-title-error` : undefined}
            aria-invalid={Boolean(errors.title)}
            autoComplete="off"
            autoFocus={autoFocus}
            disabled={isSubmitting}
            id={`${idPrefix}-subject`}
            maxLength={TITLE_MAX_LENGTH}
            onChange={(event) => {
              setTitle(event.target.value);
              if (errors.title) setErrors((current) => ({ ...current, title: undefined }));
            }}
            placeholder={t("简要描述你遇到的问题或建议")}
            value={title}
          />
          {errors.title && (
            <p className="feedback-form__error" id={`${idPrefix}-title-error`}>
              {errors.title}
            </p>
          )}
        </div>

        <div className="feedback-form__field">
          <div className="feedback-form__field-heading">
            <label htmlFor={`${idPrefix}-content`}>{t("内容")}</label>
            <span aria-live="polite">
              {content.length} / {CONTENT_MAX_LENGTH}
            </span>
          </div>
          <textarea
            aria-describedby={errors.content ? `${idPrefix}-content-error` : undefined}
            aria-invalid={Boolean(errors.content)}
            disabled={isSubmitting}
            id={`${idPrefix}-content`}
            maxLength={CONTENT_MAX_LENGTH}
            onChange={(event) => {
              setContent(event.target.value);
              if (errors.content) setErrors((current) => ({ ...current, content: undefined }));
            }}
            placeholder={t("请详细描述问题、复现步骤或你的建议...")}
            rows={5}
            value={content}
          />
          {errors.content && (
            <p className="feedback-form__error" id={`${idPrefix}-content-error`}>
              {errors.content}
            </p>
          )}
        </div>

        <footer className="feedback-form__actions">
          <button
            className="button button--outline"
            disabled={isSubmitting}
            onClick={cancelForm}
            type="button"
          >
            {t("取消")}
          </button>
          <button className="button button--primary" disabled={isSubmitting} type="submit">
            {isSubmitting ? (
              <>
                <span aria-hidden="true" className="feedback-form__spinner" />
                {t("提交中...")}
              </>
            ) : (
              <>
                <PlatformIcon name="send" size={16} />
                {t("提交")}
              </>
            )}
          </button>
        </footer>
      </form>
    </>
  );
}
