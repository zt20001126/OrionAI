import { lazy, Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { AmbientBackground } from "../../components/AmbientBackground";
import { useToast } from "../../components/ToastProvider";
import { ProductIntro } from "./ProductIntro";
import { LanguageSwitcher } from "../../i18n/LanguageSwitcher";
import { t } from "../../i18n/localeStore";
import { DemoAccountDialog } from "./DemoAccountDialog";
import { AuthAssistantShowcase } from "./components/AuthAssistantShowcase";
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

const HomeDigitalHuman = lazy(() =>
  import("./HomeDigitalHuman").then((module) => ({ default: module.HomeDigitalHuman })),
);

type AuthView = "login" | "register" | "password_reset";

interface AuthPageProps {
  initialMessage?: string | null;
  initialSuccessMessage?: string | null;
  onAuthenticated: (identity: AuthIdentity, method: AuthMethod) => void | Promise<void>;
}

const viewContent: Record<AuthView, { title: string; subtitle?: string }> = {
  login: { title: "登录 OrionAI" },
  register: { title: "注册 OrionAI" },
  password_reset: { title: "重置密码", subtitle: "通过邮箱验证码设置新密码。" },
};

/** 渲染邮箱认证和第三方登录入口；输入认证回调与提示；调用方：应用认证路由。 */
export function AuthPage({
  initialMessage,
  initialSuccessMessage,
  onAuthenticated,
}: AuthPageProps) {
  const { showToast } = useToast();
  const [view, setView] = useState<AuthView>("login");
  const [isDemoDialogOpen, setIsDemoDialogOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGuestSubmitting, setIsGuestSubmitting] = useState(false);
  const [isRequestingCode, setIsRequestingCode] = useState(false);
  const [isAuthCardHighlighted, setIsAuthCardHighlighted] = useState(false);
  const authCardRef = useRef<HTMLElement>(null);
  const authHighlightTimerRef = useRef<number | null>(null);
  const emailInputRef = useRef<HTMLInputElement>(null);

  const closeDemoDialog = useCallback(() => setIsDemoDialogOpen(false), []);
  const restoreAuthFocus = useCallback(() => emailInputRef.current?.focus(), []);

  useEffect(() => {
    if (initialMessage) showToast("error", initialMessage);
  }, [initialMessage, showToast]);

  useEffect(() => {
    if (initialSuccessMessage) showToast("success", initialSuccessMessage);
  }, [initialSuccessMessage, showToast]);

  useEffect(
    () => () => {
      if (authHighlightTimerRef.current !== null) {
        window.clearTimeout(authHighlightTimerRef.current);
      }
    },
    [],
  );

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

  /** 将访客引导回当前登录卡片，不改动表单状态或认证方式。 */
  function returnToLoginCard() {
    setIsAuthCardHighlighted(true);
    authCardRef.current?.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "start",
    });
    if (authHighlightTimerRef.current !== null) {
      window.clearTimeout(authHighlightTimerRef.current);
    }
    authHighlightTimerRef.current = window.setTimeout(() => {
      setIsAuthCardHighlighted(false);
      authHighlightTimerRef.current = null;
    }, 1200);
  }

  /** 滚动到公开功能介绍屏，并遵循系统的减少动态效果设置。 */
  function scrollToAssistant() {
    document.getElementById("auth-assistant-screen")?.scrollIntoView({
      behavior: prefersReducedMotion() ? "auto" : "smooth",
      block: "start",
    });
  }

  const content = viewContent[view];
  const needsCode = view !== "login";
  const needsConfirmation = view !== "login";

  return (
    <main className="auth-homepage">
      <section className="auth-layout auth-home-screen">
        <AmbientBackground mode="auth" />
        <ProductIntro onLogoClick={() => setIsDemoDialogOpen(true)} />
        <Suspense fallback={null}>
          <HomeDigitalHuman />
        </Suspense>
        <section className="auth-panel" aria-label={t("账号认证")}>
          <LanguageSwitcher className="language-switcher--auth" />
          <section
            aria-labelledby="auth-title"
            className={`auth-card${isAuthCardHighlighted ? " is-auth-highlighted" : ""}`}
            ref={authCardRef}
          >
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
              {content.subtitle && <p className="auth-subtitle">{t(content.subtitle)}</p>}
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
                  className="form-input auth-input-icon-space"
                  id="email"
                  maxLength={254}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="name@company.com"
                  required
                  ref={emailInputRef}
                  type="email"
                  value={email}
                />
                <MailIcon />
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
                      onChange={(event) =>
                        setCode(event.target.value.replace(/\D/g, "").slice(0, 6))
                      }
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
                    {t(
                      view === "login"
                        ? t("正在登录…")
                        : view === "register"
                          ? t("正在注册…")
                          : t("正在更新…"),
                    )}
                  </>
                ) : view === "login" ? (
                  <>
                    {t("登录")}
                    <span className="auth-submit-arrow">
                      <ArrowRightIcon />
                    </span>
                  </>
                ) : view === "register" ? (
                  t("创建账号")
                ) : (
                  t("更新密码")
                )}
              </button>
            </form>

            {view === "login" && (
              <div className="auth-guest-option">
                <div className="auth-method-divider" aria-hidden="true">
                  <span>{t("或使用其他方式登录")}</span>
                </div>
                <a
                  className="button button--outline auth-guest-button"
                  href="/api/v1/auth/gitee/login"
                >
                  <GiteeIcon />
                  {t("使用 Gitee 登录")}
                </a>
                <button
                  className="button button--outline auth-guest-button"
                  disabled={isSubmitting || isGuestSubmitting}
                  onClick={() => void handleGuestLogin()}
                  type="button"
                >
                  {isGuestSubmitting ? (
                    <>
                      <span className="button-spinner auth-guest-spinner" aria-hidden="true" />
                      {t("正在进入访客模式…")}
                    </>
                  ) : (
                    <>
                      <UserRoundIcon />
                      {t("访客登录")}
                    </>
                  )}
                </button>
              </div>
            )}
          </section>
        </section>
        <button className="auth-scroll-cue" onClick={scrollToAssistant} type="button">
          <span className="auth-scroll-cue__ring" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="m6 8 6 6 6-6M6 13l6 6 6-6" />
            </svg>
          </span>
          <span className="auth-scroll-cue__label">{t("向下探索更多功能")}</span>
        </button>
      </section>
      <AuthAssistantShowcase onRequireAuth={returnToLoginCard} />
      {view === "login" && isDemoDialogOpen && (
        <DemoAccountDialog onClose={closeDemoDialog} restoreFocus={restoreAuthFocus} />
      )}
    </main>
  );
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
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
      <div className="password-field auth-password-field">
        <LockIcon />
        <input
          autoComplete={autoComplete}
          className="form-input auth-input-icon-space"
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

/** 绘制 Gitee 品牌图标；调用方：认证页第三方登录入口。 */
function GiteeIcon() {
  return (
    <svg aria-hidden="true" className="auth-provider-icon" viewBox="0 0 24 24">
      <path
        fill="var(--auth-gitee-red)"
        d="M11.984 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12 12 12 0 0 0-12.016-12zm6.09 5.333c.328 0 .593.266.592.593v1.482a.594.594 0 0 1-.593.592H9.777c-.982 0-1.778.796-1.778 1.778v5.63c0 .327.266.592.593.592h5.63c.982 0 1.778-.796 1.778-1.778v-.296a.593.593 0 0 0-.592-.593h-4.15a.592.592 0 0 1-.592-.592v-1.482a.593.593 0 0 1 .593-.592h6.815c.327 0 .593.265.593.592v3.408a4 4 0 0 1-4 4H5.926a.593.593 0 0 1-.593-.593V9.778a4.444 4.444 0 0 1 4.445-4.444h8.296Z"
      />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg aria-hidden="true" className="auth-input-icon" viewBox="0 0 24 24">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m4 7 8 6 8-6" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg aria-hidden="true" className="auth-input-icon" viewBox="0 0 24 24">
      <rect x="4" y="10" width="16" height="11" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

function ArrowRightIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 12h15m-6-6 6 6-6 6" />
    </svg>
  );
}

function UserRoundIcon() {
  return (
    <svg aria-hidden="true" className="auth-provider-icon auth-user-icon" viewBox="0 0 24 24">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </svg>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return t("网络连接异常，请检查网络后重试。");
  return t("请求失败，请稍后重试。");
}
