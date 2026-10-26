export type AuthPurpose = "register" | "password_reset";

export interface AuthSession {
  authenticated: boolean;
  account: string | null;
}

export interface AccountResponse {
  account: string;
}

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
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload.detail as unknown)
        : null;
    const message =
      typeof detail === "string"
        ? detail
        : response.status === 422
          ? "请检查填写内容是否正确。"
          : "请求失败，请稍后重试。";
    throw new ApiError(message, response.status);
  }

  return payload as T;
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
