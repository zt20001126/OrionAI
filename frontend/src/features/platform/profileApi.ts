import { ApiError } from "../auth/authApi";
import { getSafeErrorDetail } from "../../utils/safeErrorMessage";

export interface UserProfile {
  nickname: string;
  account: string;
  avatar_url: string;
  created_at: string;
  last_login_at: string | null;
}

export interface PasswordChangePayload {
  code: string;
  new_password: string;
  password_confirmation: string;
}

export interface MessageResponse {
  message: string;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload.detail as unknown)
        : null;
    const message = getUserFacingErrorMessage(detail, response.status);
    throw new ApiError(message, response.status);
  }

  return payload as T;
}

function getUserFacingErrorMessage(detail: unknown, status: number): string {
  if (status === 422) return "请检查填写内容是否正确。";
  if (status === 401) return "登录状态已失效，请刷新页面后重新登录。";
  if (status >= 500) return "服务暂时不可用，请稍后重试。";
  return getSafeErrorDetail(detail, "请求失败，请稍后重试。");
}

export async function getUserProfile(): Promise<UserProfile> {
  const response = await fetch("/api/v1/users/me", {
    credentials: "include",
  });
  return parseResponse<UserProfile>(response);
}

export async function updateUserProfile(
  nickname: string,
  avatar: File | null,
): Promise<UserProfile> {
  const formData = new FormData();
  formData.set("nickname", nickname);
  if (avatar) formData.set("avatar", avatar);

  const response = await fetch("/api/v1/users/me", {
    method: "PATCH",
    credentials: "include",
    body: formData,
  });
  return parseResponse<UserProfile>(response);
}

export async function sendPasswordChangeCode(): Promise<MessageResponse> {
  const response = await fetch("/api/v1/users/me/password/code", {
    method: "POST",
    credentials: "include",
  });
  return parseResponse<MessageResponse>(response);
}

export async function changePassword(payload: PasswordChangePayload): Promise<MessageResponse> {
  const response = await fetch("/api/v1/users/me/password", {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<MessageResponse>(response);
}
