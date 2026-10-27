import { ApiError } from "../auth/authApi";

export interface UserProfile {
  nickname: string;
  account: string;
  avatar_url: string;
  created_at: string;
  last_login_at: string | null;
}

async function parseResponse<T>(response: Response): Promise<T> {
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
