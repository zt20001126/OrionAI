import { useCallback, useEffect, useRef, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { useLocale } from "../../i18n/LocaleProvider";
import { getLocaleTag, t } from "../../i18n/localeStore";
import { PlatformIcon, type PlatformIconName } from "../platform/PlatformIcon";
import "./demo-account-dialog.css";

const DEMO_CREDENTIALS = {
  account: "admin@admin.com",
  password: "admin",
} as const;

type CredentialKey = keyof typeof DEMO_CREDENTIALS;

interface DemoAccountDialogProps {
  onClose: () => void;
  restoreFocus: () => void;
}

export function DemoAccountDialog({ onClose, restoreFocus }: DemoAccountDialogProps) {
  const { showToast } = useToast();
  const locale = useLocale();
  const [copiedCredential, setCopiedCredential] = useState<CredentialKey | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const copyResetTimerRef = useRef<number | null>(null);

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

  useEffect(
    () => () => {
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current);
      }
    },
    [],
  );

  async function handleCopyCredential(key: CredentialKey, value: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedCredential(key);
      if (copyResetTimerRef.current !== null) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      copyResetTimerRef.current = window.setTimeout(() => {
        setCopiedCredential(null);
      }, 1400);
      showToast("success", t("复制成功。"));
    } catch {
      showToast("error", t("复制失败，请重试。"));
    }
  }

  const credentials: {
    key: CredentialKey;
    value: string;
    icon: PlatformIconName;
    copyLabel: string;
  }[] = [
    {
      key: "account",
      value: DEMO_CREDENTIALS.account,
      icon: "user",
      copyLabel: t("复制账号"),
    },
    {
      key: "password",
      value: DEMO_CREDENTIALS.password,
      icon: "lock",
      copyLabel: t("复制密码"),
    },
  ];

  return (
    <div
      className="demo-account-dialog-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) dismissDialog();
      }}
    >
      <section
        aria-labelledby="demo-account-dialog-title"
        aria-modal="true"
        className="demo-account-dialog"
        lang={getLocaleTag(locale)}
        ref={dialogRef}
        role="dialog"
      >
        <button
          aria-label={t("关闭测试账号弹窗")}
          className="demo-account-dialog__close"
          onClick={dismissDialog}
          ref={closeButtonRef}
          type="button"
        >
          <PlatformIcon name="close" size={19} />
        </button>
        <h2 className="demo-account-dialog__title" id="demo-account-dialog-title">
          <PlatformIcon name="flask" size={19} />
          <span>{t("测试账号")}</span>
        </h2>
        <div className="demo-account-dialog__credentials">
          {credentials.map((credential) => (
            <div className="demo-account-dialog__credential" key={credential.key}>
              <PlatformIcon name={credential.icon} size={20} />
              <code>{credential.value}</code>
              <button
                aria-label={credential.copyLabel}
                className="demo-account-dialog__copy"
                onClick={() => void handleCopyCredential(credential.key, credential.value)}
                type="button"
              >
                <PlatformIcon
                  name={copiedCredential === credential.key ? "check" : "copy"}
                  size={18}
                />
              </button>
            </div>
          ))}
        </div>
        <div className="demo-account-dialog__actions">
          <button className="button button--primary" onClick={dismissDialog} type="button">
            {t("我知道了")}
          </button>
        </div>
      </section>
    </div>
  );
}
