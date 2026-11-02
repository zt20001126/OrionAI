import { useCallback, useEffect, useRef } from "react";

import { useToast } from "../../components/ToastProvider";
import { t } from "../../i18n/localeStore";
import { PlatformIcon } from "../platform/PlatformIcon";
import "./demo-account-dialog.css";

const DEMO_ACCOUNT = "admin@admin.com";

interface DemoAccountDialogProps {
  onClose: () => void;
  restoreFocus: () => void;
}

export function DemoAccountDialog({ onClose, restoreFocus }: DemoAccountDialogProps) {
  const { showToast } = useToast();
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const dismissDialog = useCallback(() => {
    onClose();
    window.requestAnimationFrame(restoreFocus);
  }, [onClose, restoreFocus]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function handleDialogKeys(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        dismissDialog();
        return;
      }

      if (event.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), [href], [tabindex]:not([tabindex="-1"])',
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

  async function handleCopyAccount() {
    try {
      await navigator.clipboard.writeText(DEMO_ACCOUNT);
      showToast("success", t("体验账号已复制。"));
    } catch {
      showToast("error", t("复制失败，请手动复制账号。"));
    }
  }

  return (
    <div
      className="demo-account-dialog-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) dismissDialog();
      }}
    >
      <section
        aria-describedby="demo-account-dialog-description"
        aria-labelledby="demo-account-dialog-title"
        aria-modal="true"
        className="demo-account-dialog"
        ref={dialogRef}
        role="dialog"
      >
        <button
          aria-label={t("关闭体验账号提示")}
          className="demo-account-dialog__close"
          onClick={dismissDialog}
          ref={closeButtonRef}
          type="button"
        >
          <PlatformIcon name="close" size={19} />
        </button>
        <h2 id="demo-account-dialog-title">{t("体验账号")}</h2>
        <div className="demo-account-dialog__credentials">
          <div className="demo-account-dialog__field">
            <span className="demo-account-dialog__label">{t("账号")}</span>
            <div className="demo-account-dialog__account-row">
              <code>{DEMO_ACCOUNT}</code>
              <button
                className="button button--outline demo-account-dialog__copy"
                onClick={() => void handleCopyAccount()}
                type="button"
              >
                {t("复制账号")}
              </button>
            </div>
          </div>
          <div className="demo-account-dialog__field">
            <span className="demo-account-dialog__label">{t("密码")}</span>
            <code>admin</code>
          </div>
        </div>
        <p id="demo-account-dialog-description">
          {t("可体验会员功能。此账号为共享演示数据，请勿保存个人信息。")}
        </p>
        <div className="demo-account-dialog__actions">
          <button className="button button--primary" onClick={dismissDialog} type="button">
            {t("我知道了")}
          </button>
        </div>
      </section>
    </div>
  );
}
