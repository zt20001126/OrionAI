import { useEffect, useState, type FormEvent } from "react";

import { useToast } from "../../components/ToastProvider";
import { ApiError } from "../auth/authApi";
import { changePassword, sendPasswordChangeCode } from "./profileApi";

interface SecuritySettingsPageProps {
  account: string;
  hidden?: boolean;
  onDirtyChange?: (isDirty: boolean) => void;
  onPasswordChanged: (message: string) => void;
}

/** 安全设置页，仅处理当前账号的登录密码修改。 */
export function SecuritySettingsPage({
  account,
  hidden = false,
  onDirtyChange,
  onPasswordChanged,
}: SecuritySettingsPageProps) {
  const { showToast } = useToast();
  const [newPassword, setNewPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [code, setCode] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showPasswordConfirmation, setShowPasswordConfirmation] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [isSendingCode, setIsSendingCode] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isDirty = Boolean(newPassword || passwordConfirmation || code);
  const passwordLength = Array.from(newPassword).length;
  const passwordIsValid =
    passwordLength >= 8 && passwordLength <= 64 && newPassword.trim().length > 0;

  useEffect(() => {
    onDirtyChange?.(isDirty);
  }, [isDirty, onDirtyChange]);

  useEffect(() => {
    if (countdown <= 0) return;
    const timer = window.setInterval(() => {
      setCountdown((remaining) => Math.max(0, remaining - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [countdown]);

  function clearFeedback() {
    setErrorMessage(null);
  }

  function cancelChanges() {
    setNewPassword("");
    setPasswordConfirmation("");
    setCode("");
    clearFeedback();
  }

  async function sendCode() {
    setIsSendingCode(true);
    clearFeedback();
    try {
      const result = await sendPasswordChangeCode();
      setCountdown(60);
      showToast("success", result.message || `验证码已发送至 ${account}。`);
    } catch (error) {
      showToast("error", getPasswordSettingsErrorMessage(error, "验证码发送失败，请稍后重试。"));
    } finally {
      setIsSendingCode(false);
    }
  }

  async function submitPasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    clearFeedback();

    if (!passwordIsValid) {
      setErrorMessage("密码长度须为 8 到 64 个字符，且不能仅由空格组成。");
      return;
    }
    if (newPassword !== passwordConfirmation) {
      setErrorMessage("两次输入的密码不一致。");
      return;
    }
    if (!/^\d{6}$/.test(code)) {
      setErrorMessage("请输入 6 位邮箱验证码。");
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await changePassword({
        code,
        new_password: newPassword,
        password_confirmation: passwordConfirmation,
      });
      setNewPassword("");
      setPasswordConfirmation("");
      setCode("");
      onPasswordChanged(result.message);
    } catch (error) {
      showToast("error", getPasswordSettingsErrorMessage(error, "密码修改失败，请稍后重试。"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <section
      aria-labelledby="security-settings-title"
      className="profile-settings-page"
      hidden={hidden}
    >
      <form
        className="profile-settings security-settings"
        onSubmit={(event) => void submitPasswordChange(event)}
      >
        <header className="profile-settings__header">
          <h1 id="security-settings-title">安全设置</h1>
        </header>

        <div className="security-settings__intro">
          <h2>修改登录密码</h2>
          <p>为了保障账号安全，修改密码前需要验证账号绑定的邮箱。</p>
        </div>

        <div className="security-settings__fields">
          <label className="profile-settings__field">
            <span>绑定邮箱</span>
            <input className="form-input" readOnly value={account} />
          </label>

          <label className="profile-settings__field">
            <span>新密码</span>
            <span className="password-field">
              <input
                aria-label="新密码"
                autoComplete="new-password"
                className="form-input"
                disabled={isSubmitting}
                minLength={8}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  if (Array.from(value).length <= 64) setNewPassword(value);
                  clearFeedback();
                }}
                required
                type={showNewPassword ? "text" : "password"}
                value={newPassword}
              />
              <button
                aria-label={showNewPassword ? "隐藏新密码" : "显示新密码"}
                className="password-toggle security-settings__password-toggle"
                onClick={() => setShowNewPassword((visible) => !visible)}
                type="button"
              >
                {showNewPassword ? "隐藏" : "显示"}
              </button>
            </span>
            <small>8–64 个字符，不能仅使用空格。</small>
          </label>

          <label className="profile-settings__field">
            <span>确认新密码</span>
            <span className="password-field">
              <input
                aria-label="确认新密码"
                autoComplete="new-password"
                className="form-input"
                disabled={isSubmitting}
                minLength={8}
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  if (Array.from(value).length <= 64) setPasswordConfirmation(value);
                  clearFeedback();
                }}
                required
                type={showPasswordConfirmation ? "text" : "password"}
                value={passwordConfirmation}
              />
              <button
                aria-label={showPasswordConfirmation ? "隐藏确认密码" : "显示确认密码"}
                className="password-toggle security-settings__password-toggle"
                onClick={() => setShowPasswordConfirmation((visible) => !visible)}
                type="button"
              >
                {showPasswordConfirmation ? "隐藏" : "显示"}
              </button>
            </span>
          </label>

          <label className="profile-settings__field">
            <span>邮箱验证码</span>
            <span className="code-row security-settings__code-row">
              <input
                aria-label="邮箱验证码"
                autoComplete="one-time-code"
                className="form-input"
                disabled={isSubmitting}
                inputMode="numeric"
                maxLength={6}
                onChange={(event) => {
                  setCode(event.currentTarget.value.replace(/\D/g, "").slice(0, 6));
                  clearFeedback();
                }}
                pattern="[0-9]{6}"
                required
                value={code}
              />
              <button
                className="button button--outline code-button"
                disabled={countdown > 0 || isSendingCode || isSubmitting}
                onClick={() => void sendCode()}
                type="button"
              >
                {isSendingCode ? "发送中…" : countdown > 0 ? `${countdown} 秒后重发` : "发送验证码"}
              </button>
            </span>
          </label>
        </div>

        <div aria-live="polite" className="profile-settings__feedback">
          {errorMessage && (
            <p className="profile-settings__message profile-settings__message--error" role="alert">
              {errorMessage}
            </p>
          )}
        </div>

        <footer className="profile-settings__actions">
          <button
            className="button button--outline"
            disabled={!isDirty || isSubmitting}
            onClick={cancelChanges}
            type="button"
          >
            取消
          </button>
          <button className="button button--primary" disabled={isSubmitting} type="submit">
            {isSubmitting ? "正在修改…" : "确认修改"}
          </button>
        </footer>
      </form>
    </section>
  );
}

function getPasswordSettingsErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return "网络连接异常，请检查网络后重试。";
  return fallback;
}
