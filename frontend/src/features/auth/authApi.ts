export type AuthPurpose = "register" | "password_reset";

export interface AuthSession {
  authenticated: boolean;
  account: string | null;
}

export interface AccountResponse {
  account: string;
}

const MAX_USER_FACING_ERROR_LENGTH = 180;
const SERVICE_UNAVAILABLE_STATUS = 503;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/auth/${path}`, {
    method: body ? "POST" : "GET",
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(getUserFacingErrorMessage(payload, response.status), response.status);
  }

  return payload as T;
}

function getUserFacingErrorMessage(payload: unknown, status: number): string {
  if (status === 422) return "请检查填写内容是否正确。";
  if (status >= 500 && status !== SERVICE_UNAVAILABLE_STATUS) {
    return "认证服务暂不可用，请稍后重试。";
  }

  const detail =
    payload && typeof payload === "object" && "detail" in payload
      ? (payload.detail as unknown)
      : null;
  if (typeof detail !== "string") return "请求失败，请稍后重试。";

  const message = detail.trim();
  const containsTechnicalDetails = /(?:traceback|stack trace|exception|error:)/i.test(message);
  if (
    !message ||
    message.length > MAX_USER_FACING_ERROR_LENGTH ||
    /[\r\n]/.test(message) ||
    containsTechnicalDetails
  ) {
    return "请求失败，请稍后重试。";
  }

  return message;
}

export function getSession(): Promise<AuthSession> {
  return request<AuthSession>("session");
}

export function requestEmailCode(
  email: string,
  purpose: AuthPurpose,
): Promise<{ message: string }> {
  return request("email-codes", { email, purpose });
}

export function register(
  email: string,
  code: string,
  password: string,
  passwordConfirmation: string,
): Promise<AccountResponse> {
  return request("register", {
    email,
    code,
    password,
    password_confirmation: passwordConfirmation,
  });
}

export function login(email: string, password: string): Promise<AccountResponse> {
  return request("login", { email, password });
}

export function resetPassword(
  email: string,
  code: string,
  newPassword: string,
  passwordConfirmation: string,
): Promise<{ message: string }> {
  return request("password-reset", {
    email,
    code,
    new_password: newPassword,
    password_confirmation: passwordConfirmation,
  });
}

export function logout(): Promise<{ message: string }> {
  return request("logout", {});
}
