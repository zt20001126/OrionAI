import { useEffect, useState, type FormEvent } from "react";

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
  onAuthenticated: (account: string) => void;
}

const viewContent: Record<AuthView, { title: string; subtitle: string }> = {
  login: { title: "登录 OrionAI", subtitle: "使用邮箱和密码继续" },
  register: { title: "创建账号", subtitle: "验证邮箱后即可开始使用" },
  password_reset: { title: "重置密码", subtitle: "我们会向你的邮箱发送一次性验证码" },
};

export function AuthPage({ initialMessage, onAuthenticated }: AuthPageProps) {
  const [view, setView] = useState<AuthView>("login");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRequestingCode, setIsRequestingCode] = useState(false);
  const [message, setMessage] = useState<string | null>(initialMessage ?? null);
  const [error, setError] = useState<string | null>(null);

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
    setError(null);
  }

  async function handleRequestCode() {
    setError(null);
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
      setError(getErrorMessage(requestError));
    } finally {
      setIsRequestingCode(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
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
      setError(getErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  }

  const content = viewContent[view];
  const needsCode = view !== "login";
  const needsConfirmation = view !== "login";

  return (
    <main className="auth-shell">
      <section className="auth-card" aria-labelledby="auth-title">
        <div className="brand-mark" aria-hidden="true">
          O
        </div>
        <p className="eyebrow">ORIONAI PLATFORM</p>
        <h1 id="auth-title">{content.title}</h1>
        <p className="auth-subtitle">{content.subtitle}</p>

        {message && (
          <p className="form-message success-message" role="status">
            {message}
          </p>
        )}
        {error && (
          <p className="form-message error-message" role="alert">
            {error}
          </p>
        )}

        <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
          <label htmlFor="email">邮箱</label>
          <input
            autoComplete="email"
            id="email"
            maxLength={254}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@example.com"
            required
            type="email"
            value={email}
          />

          {needsCode && (
            <>
              <label htmlFor="verification-code">邮箱验证码</label>
              <div className="code-row">
                <input
                  autoComplete="one-time-code"
                  id="verification-code"
                  inputMode="numeric"
                  maxLength={6}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  pattern="[0-9]{6}"
                  placeholder="6 位数字"
                  required
                  value={code}
                />
                <button
                  className="secondary-button code-button"
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
            </>
          )}

          <label htmlFor="password">{view === "password_reset" ? "新密码" : "密码"}</label>
          <input
            autoComplete={view === "login" ? "current-password" : "new-password"}
            id="password"
            maxLength={128}
            minLength={view === "login" ? 1 : 8}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={view === "login" ? "请输入密码" : "至少 8 个字符"}
            required
            type="password"
            value={password}
          />

          {needsConfirmation && (
            <>
              <label htmlFor="password-confirmation">确认密码</label>
              <input
                autoComplete="new-password"
                id="password-confirmation"
                maxLength={128}
                minLength={8}
                onChange={(event) => setPasswordConfirmation(event.target.value)}
                placeholder="再次输入密码"
                required
                type="password"
                value={passwordConfirmation}
              />
            </>
          )}

          <button className="primary-button submit-button" disabled={isSubmitting} type="submit">
            {isSubmitting
              ? "请稍候…"
              : view === "login"
                ? "登录"
                : view === "register"
                  ? "注册并登录"
                  : "更新密码"}
          </button>
        </form>

        <nav className="auth-links" aria-label="认证选项">
          {view === "login" ? (
            <>
              <button onClick={() => changeView("password_reset")} type="button">
                忘记密码？
              </button>
              <span aria-hidden="true">·</span>
              <button onClick={() => changeView("register")} type="button">
                创建账号
              </button>
            </>
          ) : (
            <button onClick={() => changeView("login")} type="button">
              返回登录
            </button>
          )}
        </nav>
        <p className="auth-security-note">
          登录状态由安全 Cookie 保存，不会将会话令牌暴露给页面脚本。
        </p>
      </section>
    </main>
  );
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "请求失败，请稍后重试。";
}
