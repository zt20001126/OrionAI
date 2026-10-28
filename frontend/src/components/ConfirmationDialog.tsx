import { useEffect, useRef } from "react";

import "./confirmation-dialog.css";

export interface ConfirmOptions {
  title: string;
  description: string;
  cancelLabel?: string;
  confirmLabel?: string;
  tone?: "warning" | "danger";
  onConfirm?: () => boolean | void | Promise<boolean | void>;
}

interface ConfirmationDialogProps {
  confirmation: ConfirmOptions;
  errorMessage: string | null;
  isBusy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmationDialog({
  confirmation,
  errorMessage,
  isBusy,
  onCancel,
  onConfirm,
}: ConfirmationDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const handlersRef = useRef({ onCancel, onConfirm });

  useEffect(() => {
    handlersRef.current = { onCancel, onConfirm };
  }, [onCancel, onConfirm]);

  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    cancelButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        handlersRef.current.onCancel();
        return;
      }

      if (event.key !== "Tab") return;
      const buttons =
        dialogRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)");
      if (!buttons?.length) {
        event.preventDefault();
        dialogRef.current?.focus();
        return;
      }

      const firstButton = buttons[0];
      const lastButton = buttons[buttons.length - 1];
      const focusIsInsideDialog = dialogRef.current?.contains(document.activeElement) ?? false;
      if (
        event.shiftKey &&
        (document.activeElement === firstButton ||
          document.activeElement === dialogRef.current ||
          !focusIsInsideDialog)
      ) {
        event.preventDefault();
        lastButton.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === lastButton ||
          document.activeElement === dialogRef.current ||
          !focusIsInsideDialog)
      ) {
        event.preventDefault();
        firstButton.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, []);

  useEffect(() => {
    if (isBusy) dialogRef.current?.focus();
  }, [isBusy]);

  const tone = confirmation.tone ?? "warning";

  return (
    <div
      className="confirmation-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) handlersRef.current.onCancel();
      }}
    >
      <section
        aria-describedby="confirmation-description"
        aria-labelledby="confirmation-title"
        aria-modal="true"
        aria-busy={isBusy}
        className={`confirmation-dialog confirmation-dialog--${tone}`}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <div aria-hidden="true" className="confirmation-dialog__icon">
          <ConfirmationIcon tone={tone} />
        </div>
        <div className="confirmation-dialog__content">
          <h2 id="confirmation-title">{confirmation.title}</h2>
          <p id="confirmation-description">{confirmation.description}</p>
          {errorMessage && (
            <p className="confirmation-dialog__error" role="alert">
              {errorMessage}
            </p>
          )}
        </div>
        <div className="confirmation-dialog__actions">
          <button
            className="button button--outline"
            disabled={isBusy}
            onClick={onCancel}
            ref={cancelButtonRef}
            type="button"
          >
            {confirmation.cancelLabel ?? "取消"}
          </button>
          <button
            className={`button ${tone === "danger" ? "button--danger" : "button--primary"}`}
            disabled={isBusy}
            onClick={onConfirm}
            type="button"
          >
            {isBusy ? "处理中…" : (confirmation.confirmLabel ?? "确认")}
          </button>
        </div>
      </section>
    </div>
  );
}

function ConfirmationIcon({ tone }: { tone: "warning" | "danger" }) {
  return (
    <svg viewBox="0 0 24 24" fill="none">
      {tone === "warning" ? (
        <>
          <path d="m12 3 9 16H3l9-16Z" />
          <path d="M12 9v4M12 16h.01" />
        </>
      ) : (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v5M12 16h.01" />
        </>
      )}
    </svg>
  );
}
