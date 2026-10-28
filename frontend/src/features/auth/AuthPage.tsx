import { useEffect, useState, type FormEvent } from "react";

import { useToast } from "../../components/ToastProvider";
import { BrandMark, ProductIntro } from "./ProductIntro";
import {
  ApiError,
  login,
  register,
  requestEmailCode,
  resetPassword,
  type AuthPurpose,
} from "./authApi";

type AuthView = "login" | "register" | "password_reset";

interface AuthPageProps {
  initialMessage?: string | null;
  initialSuccessMessage?: string | null;
  onAuthenticated: (account: string) => void;
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
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRequestingCode, setIsRequestingCode] = useState(false);
  const [message, setMessage] = useState<string | null>(initialSuccessMessage ?? null);

  useEffect(() => {
    if (initialMessage) showToast("error", initialMessage);
  }, [initialMessage, showToast]);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((seconds) => seconds - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  function changeView(nextView: AuthView) {
    setView(nextView);
    setCode("");
    setPassword("");
    setPasswordConfirmation("");
    setCooldown(0);
    setMessage(null);
  }

  async function handleRequestCode() {
    setMessage(null);
    setIsRequestingCode(true);
    try {
      const purpose: AuthPurpose = view === "register" ? "register" : "password_reset";
      const result = await requestEmailCode(email, purpose);
      setCooldown(60);
      setMessage(result.message);
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
    setMessage(null);
    setIsSubmitting(true);
    try {
      if (view === "login") {
        const result = await login(email, password);
        onAuthenticated(result.account);
      } else if (view === "register") {
        const result = await register(email, code, password, passwordConfirmation);
        onAuthenticated(result.account);
      } else {
        const result = await resetPassword(email, code, password, passwordConfirmation);
        changeView("login");
        setMessage(result.message);
      }
    } catch (submitError) {
      showToast("error", getErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  const content = viewContent[view];
  const needsCode = view !== "login";
  const needsConfirmation = view !== "login";

  return (
    <main className="auth-layout">
      <ProductIntro />
      <section className="auth-panel" aria-label="账号认证">
        <section className="auth-card" aria-labelledby="auth-title">
          <div className="auth-card-brand">
            <BrandMark />
            <span>OrionAI</span>
          </div>

          {view !== "password_reset" ? (
            <div className="auth-tabs" role="tablist" aria-label="登录或注册">
              <button
                aria-controls="auth-form-panel"
                aria-selected={view === "login"}
                className={`auth-tab${view === "login" ? " is-active" : ""}`}
                id="auth-tab-login"
                onClick={() => changeView("login")}
                role="tab"
                type="button"
              >
                登录
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
                注册
              </button>
            </div>
          ) : (
            <button className="back-link" onClick={() => changeView("login")} type="button">
              <ChevronLeftIcon />
              返回登录
            </button>
          )}

          <div className="auth-heading">
            <h2 id="auth-title">{content.title}</h2>
            <p className="auth-subtitle">{content.subtitle}</p>
          </div>

          {message && (
            <p className="form-message success-message" role="status">
              {message}
            </p>
          )}
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
                邮箱
              </label>
              <input
                autoComplete="email"
                className="form-input"
                id="email"
                maxLength={254}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@company.com"
                required
                type="email"
                value={email}
              />
            </div>

            {needsCode && (
              <div className="form-field">
                <label className="form-label" htmlFor="verification-code">
                  邮箱验证码
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
                    placeholder="输入 6 位验证码"
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
                      ? "发送中…"
                      : cooldown > 0
                        ? `${cooldown} 秒后重发`
                        : "获取验证码"}
                  </button>
                </div>
              </div>
            )}

            <PasswordField
              autoComplete={view === "login" ? "current-password" : "new-password"}
              id="password"
              label={view === "password_reset" ? "新密码" : "密码"}
              maxLength={128}
              minLength={view === "login" ? 1 : 8}
              onChange={setPassword}
              placeholder={view === "login" ? "请输入密码" : "至少 8 个字符"}
              value={password}
            />

            {needsConfirmation && (
              <PasswordField
                autoComplete="new-password"
                id="password-confirmation"
                label="确认密码"
                maxLength={128}
                minLength={8}
                onChange={setPasswordConfirmation}
                placeholder="再次输入密码"
                value={passwordConfirmation}
              />
            )}

            {view === "login" && (
              <div className="form-options">
                <span>使用注册邮箱登录</span>
                <button
                  className="text-link"
                  onClick={() => changeView("password_reset")}
                  type="button"
                >
                  忘记密码？
                </button>
              </div>
            )}

            <button
              className="button button--primary submit-button"
              disabled={isSubmitting}
              type="submit"
            >
              {isSubmitting ? (
                <>
                  <span className="button-spinner" aria-hidden="true" />
                  {view === "login" ? "正在登录…" : view === "register" ? "正在注册…" : "正在更新…"}
                </>
              ) : view === "login" ? (
                "登录"
              ) : view === "register" ? (
                "创建账号"
              ) : (
                "更新密码"
              )}
            </button>
          </form>

          <p className="auth-security-note">
            <ShieldIcon />
            <span>安全加密连接 · 会话仅保存在安全 Cookie 中</span>
          </p>
        </section>
      </section>
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
          aria-label={isVisible ? "隐藏密码" : "显示密码"}
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
  if (error instanceof TypeError) return "网络连接异常，请检查网络后重试。";
  return "请求失败，请稍后重试。";
}
