/** 为头像菜单中的问题反馈入口提供模态容器和键盘焦点管理。 */

import { useCallback, useEffect, useRef, useState } from "react";

import { PlatformIcon } from "../platform/PlatformIcon";
import { FeedbackForm } from "./FeedbackForm";
import "./feedback.css";

interface FeedbackDialogProps {
  onClose: () => void;
  restoreFocus: () => void;
}

/** 头像菜单仍以弹窗呈现，并将表单逻辑交给设置页共用的 FeedbackForm。 */
export function FeedbackDialog({ onClose, restoreFocus }: FeedbackDialogProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isSubmittingRef = useRef(false);
  const dialogRef = useRef<HTMLElement>(null);

  const handleSubmittingChange = useCallback((submitting: boolean) => {
    isSubmittingRef.current = submitting;
    setIsSubmitting(submitting);
  }, []);

  const dismissDialog = useCallback(() => {
    if (isSubmittingRef.current) return;
    onClose();
    window.requestAnimationFrame(restoreFocus);
  }, [onClose, restoreFocus]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleDialogKeys(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        dismissDialog();
        return;
      }

      if (event.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        "button:not(:disabled), input:not(:disabled), textarea:not(:disabled)",
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleDialogKeys);
    return () => {
      document.removeEventListener("keydown", handleDialogKeys);
      document.body.style.overflow = previousOverflow;
    };
  }, [dismissDialog]);

  return (
    <div
      className="dialog-backdrop feedback-dialog-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) dismissDialog();
      }}
    >
      <section
        aria-describedby="feedback-dialog-description"
        aria-labelledby="feedback-dialog-title"
        aria-modal="true"
        className="feedback-dialog"
        ref={dialogRef}
        role="dialog"
      >
        <button
          aria-label="关闭问题反馈"
          className="dialog-close"
          disabled={isSubmitting}
          onClick={dismissDialog}
          type="button"
        >
          <PlatformIcon name="close" size={19} />
        </button>
        <FeedbackForm
          autoFocus
          onCancel={dismissDialog}
          onSubmittingChange={handleSubmittingChange}
          onSuccess={dismissDialog}
          variant="dialog"
        />
      </section>
    </div>
  );
}
