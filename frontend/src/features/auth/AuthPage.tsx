import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { useToast } from "../../components/ToastProvider";
import { BrandMark, ProductIntro } from "./ProductIntro";
import { LanguageSwitcher } from "../../i18n/LanguageSwitcher";
import { t } from "../../i18n/localeStore";
import { DemoAccountDialog } from "./DemoAccountDialog";
import {
  ApiError,
  guestLogin,
  login,
  register,
  requestEmailCode,
  resetPassword,
  type AuthMethod,
  type AuthPurpose,
  type AuthIdentity,
} from "./authApi";

type AuthView = "login" | "register" | "password_reset";

interface AuthPageProps {
  initialMessage?: string | null;
  initialSuccessMessage?: string | null;
  onAuthenticated: (identity: AuthIdentity, method: AuthMethod) => void | Promise<void>;
}

const viewContent: Record<AuthView, { title: string; subtitle: string }> = {
  login: { title: "登录 OrionAI", subtitle: "欢迎回来，请登录你的工作空间。" },
  register: { title: "创建你的账号", subtitle: "验证邮箱，开启 AI 智能体开发。" },
  password_reset: { title: "重置密码", subtitle: "通过邮箱验证码设置新密码。" },
};

export function AuthPage({
  initialMessage,
  initialSuccessMessage,
  onAuthenticated,
}: AuthPageProps) {
  const { showToast } = useToast();
  const [view, setView] = useState<AuthView>("login");
  const [isDemoDialogOpen, setIsDemoDialogOpen] = useState(true);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGuestSubmitting, setIsGuestSubmitting] = useState(false);
  const [isRequestingCode, setIsRequestingCode] = useState(false);
  const emailInputRef = useRef<HTMLInputElement>(null);

  const closeDemoDialog = useCallback(() => setIsDemoDialogOpen(false), []);
  const restoreAuthFocus = useCallback(() => emailInputRef.current?.focus(), []);

  useEffect(() => {
    if (initialMessage) showToast("error", initialMessage);
  }, [initialMessage, showToast]);

  useEffect(() => {
    if (initialSuccessMessage) showToast("success", initialSuccessMessage);
  }, [initialSuccessMessage, showToast]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((seconds) => seconds - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  function changeView(nextView: AuthView) {
    setIsDemoDialogOpen(false);
    setView(nextView);
    setCode("");
    setPassword("");
    setPasswordConfirmation("");
    setCooldown(0);
  }

  async function handleRequestCode() {
    setIsRequestingCode(true);
    try {
      const purpose: AuthPurpose = view === "register" ? "register" : "password_reset";
      const result = await requestEmailCode(email, purpose);
      setCooldown(60);
      showToast("success", result.message);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 429) {
        setCooldown(60);
      }
      showToast("error", getErrorMessage(requestError));
    } finally {
      setIsRequestingCode(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      if (view === "login") {
        const result = await login(email, password);
        await onAuthenticated({ account: result.account, is_guest: false }, "login");
      } else if (view === "register") {
        const result = await register(email, code, password, passwordConfirmation);
        await onAuthenticated({ account: result.account, is_guest: false }, "register");
      } else {
        const result = await resetPassword(email, code, password, passwordConfirmation);
        changeView("login");
        showToast("success", result.message);
      }
    } catch (submitError) {
      showToast("error", getErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleGuestLogin() {
    setIsGuestSubmitting(true);
    try {
      const session = await guestLogin();
      await onAuthenticated(
        { account: session.account, is_guest: session.is_guest === true },
        "guest",
      );
    } catch (loginError) {
      showToast("error", getErrorMessage(loginError));
    } finally {
      setIsGuestSubmitting(false);
    }
  }

  const content = viewContent[view];
  const needsCode = view !== "login";
  const needsConfirmation = view !== "login";

  return (
    <main className="auth-layout">
      <ProductIntro />
      <section className="auth-panel" aria-label={t("账号认证")}>
        <LanguageSwitcher className="language-switcher--auth" />
        <section className="auth-card" aria-labelledby="auth-title">
          <div className="auth-card-brand">
            <BrandMark />
              <span>OrionAI</span>
          </div>

          {view !== "password_reset" ? (
            <div className="auth-tabs" role="tablist" aria-label={t("登录或注册")}>
              <button
                aria-controls="auth-form-panel"
                aria-selected={view === "login"}
                className={`auth-tab${view === "login" ? " is-active" : ""}`}
                id="auth-tab-login"
                onClick={() => changeView("login")}
                role="tab"
                type="button"
              >
                {t("登录")}
              </button>
              <button
                aria-controls="auth-form-panel"
                aria-selected={view === "register"}
                className={`auth-tab${view === "register" ? " is-active" : ""}`}
                id="auth-tab-register"
                onClick={() => changeView("register")}
                role="tab"
                type="button"
              >
                {t("注册")}
              </button>
            </div>
          ) : (
            <button className="back-link" onClick={() => changeView("login")} type="button">
              <ChevronLeftIcon />
              {t("返回登录")}
            </button>
          )}

          <div className="auth-heading">
            <h2 id="auth-title">{t(content.title)}</h2>
            <p className="auth-subtitle">{t(content.subtitle)}</p>
          </div>

          <form
            aria-busy={isSubmitting}
            className="auth-form"
            id="auth-form-panel"
            onSubmit={(event) => void handleSubmit(event)}
            role={view === "password_reset" ? undefined : "tabpanel"}
            aria-labelledby={
              view === "password_reset"
                ? "auth-title"
                : view === "register"
                  ? "auth-tab-register"
                  : "auth-tab-login"
            }
          >
            <div className="form-field">
              <label className="form-label" htmlFor="email">
                {t("邮箱")}
              </label>
              <input
                autoComplete="email"
                className="form-input"
                id="email"
                maxLength={254}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
                required
                ref={emailInputRef}
                type="email"
                value={email}
              />
            </div>

            {needsCode && (
              <div className="form-field">
                <label className="form-label" htmlFor="verification-code">
                  {t("邮箱验证码")}
                </label>
                <div className="code-row">
                  <input
                    autoComplete="one-time-code"
                    className="form-input code-input"
                    id="verification-code"
                    inputMode="numeric"
                    maxLength={6}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    pattern="[0-9]{6}"
                    placeholder={t("输入 6 位验证码")}
                    required
                    value={code}
                  />
                  <button
                    className="button button--outline code-button"
                    disabled={isRequestingCode || cooldown > 0 || !email.trim()}
                    onClick={() => void handleRequestCode()}
                    type="button"
                  >
                    {isRequestingCode
                      ? t("发送中…")
                      : cooldown > 0
                        ? t("{seconds} 秒后重发", { seconds: cooldown })
                        : t("获取验证码")}
                  </button>
                </div>
              </div>
            )}

            <PasswordField
              autoComplete={view === "login" ? "current-password" : "new-password"}
              id="password"
              label={t(view === "password_reset" ? t("新密码") : t("密码"))}
              maxLength={128}
              minLength={view === "login" ? 1 : 8}
              onChange={setPassword}
              placeholder={t(view === "login" ? t("请输入密码") : t("至少 8 个字符"))}
              value={password}
            />

            {needsConfirmation && (
              <PasswordField
                autoComplete="new-password"
                id="password-confirmation"
                label={t("确认密码")}
                maxLength={128}
                minLength={8}
                onChange={setPasswordConfirmation}
                placeholder={t("再次输入密码")}
                value={passwordConfirmation}
              />
            )}

            {view === "login" && (
              <div className="form-options">
                <span>{t("使用注册邮箱登录")}</span>
                <button
                  className="text-link"
                  onClick={() => changeView("password_reset")}
                  type="button"
                >
                  {t("忘记密码？")}
                </button>
              </div>
            )}

            <button
              className="button button--primary submit-button"
              disabled={isSubmitting || isGuestSubmitting}
              type="submit"
            >
              {isSubmitting ? (
                <>
                  <span className="button-spinner" aria-hidden="true" />
                  {t(view === "login" ? t("正在登录…") : view === "register" ? t("正在注册…") : t("正在更新…"))}
                </>
              ) : view === "login" ? (
                t("登录")
              ) : view === "register" ? (
                t("创建账号")
              ) : (
                t("更新密码")
              )}
            </button>
          </form>

          {view === "login" && (
            <div className="auth-guest-option">
              <div className="auth-guest-divider" aria-hidden="true">
                <span>{t("或")}</span>
              </div>
              <button
                className="button button--outline auth-guest-button"
                disabled={isSubmitting || isGuestSubmitting}
                onClick={() => void handleGuestLogin()}
                type="button"
              >
                {isGuestSubmitting ? (
                  <>
                    <span className="button-spinner auth-guest-spinner" aria-hidden="true" />
                    {t("正在进入访客空间…")}
                  </>
                ) : (
                  t("以访客身份体验")
                )}
              </button>
              <p className="auth-guest-note">
                {t("无需注册 · 会话默认有效 7 天，清除 Cookie 后无法恢复访客数据")}
              </p>
            </div>
          )}

          <p className="auth-security-note">
            <ShieldIcon />
            <span>{t("安全加密连接 · 会话仅保存在安全 Cookie 中")}</span>
          </p>
        </section>
      </section>
      {view === "login" && isDemoDialogOpen && (
        <DemoAccountDialog onClose={closeDemoDialog} restoreFocus={restoreAuthFocus} />
      )}
    </main>
  );
}

interface PasswordFieldProps {
  autoComplete: string;
  id: string;
  label: string;
  maxLength: number;
  minLength: number;
  onChange: (value: string) => void;
  placeholder: string;
  value: string;
}

function PasswordField({
  autoComplete,
  id,
  label,
  maxLength,
  minLength,
  onChange,
  placeholder,
  value,
}: PasswordFieldProps) {
  const [isVisible, setIsVisible] = useState(false);

  return (
    <div className="form-field">
      <label className="form-label" htmlFor={id}>
        {label}
      </label>
      <div className="password-field">
        <input
          autoComplete={autoComplete}
          className="form-input"
          id={id}
          maxLength={maxLength}
          minLength={minLength}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          required
          type={isVisible ? "text" : "password"}
          value={value}
        />
        <button
          aria-label={t(isVisible ? t("隐藏密码") : t("显示密码"))}
          aria-pressed={isVisible}
          className="password-toggle"
          onClick={() => setIsVisible((visible) => !visible)}
          type="button"
        >
          <EyeIcon visible={isVisible} />
        </button>
      </div>
    </div>
  );
}

function EyeIcon({ visible }: { visible: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M2.5 12s3.3-6 9.5-6 9.5 6 9.5 6-3.3 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.6" />
      {!visible && <path d="m4 4 16 16" />}
    </svg>
  );
}

function ChevronLeftIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="m12.5 4.5-5.5 5.5 5.5 5.5" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M10 2.5 16 5v4.4c0 3.7-2.5 6.4-6 8.1-3.5-1.7-6-4.4-6-8.1V5l6-2.5Z" />
      <path d="m7.5 9.8 1.7 1.7 3.5-3.5" />
    </svg>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return t("网络连接异常，请检查网络后重试。");
  return t("请求失败，请稍后重试。");
}
