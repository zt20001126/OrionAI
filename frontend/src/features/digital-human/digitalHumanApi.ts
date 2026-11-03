import { getSafeErrorDetail } from "../../utils/safeErrorMessage";
import { t } from "../../i18n/localeStore";

import type { DigitalHumanConversationListResponse, TranscriptionResponse } from "./types";

export class DigitalHumanApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "DigitalHumanApiError";
  }
}

export async function listDigitalHumanConversations(
  offset = 0,
  limit = 50,
): Promise<DigitalHumanConversationListResponse> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  const response = await fetch(`/api/digital-human/conversations?${query.toString()}`, {
    credentials: "include",
  });
  return readJsonResponse<DigitalHumanConversationListResponse>(response);
}

export async function recognizeSpeech(
  audio: Blob,
  signal?: AbortSignal,
): Promise<TranscriptionResponse> {
  const form = new FormData();
  const extension = audio.type.includes("webm")
    ? "webm"
    : audio.type.includes("ogg")
      ? "ogg"
      : audio.type.includes("mp4")
        ? "mp4"
        : audio.type.includes("mpeg")
          ? "mp3"
          : "wav";
  form.append("file", audio, `recording.${extension}`);

  let response: Response;
  try {
    response = await fetch("/api/digital-human/speech/recognitions", {
      method: "POST",
      credentials: "include",
      body: form,
      signal,
    });
  } catch {
    throw new DigitalHumanApiError(t("暂时无法连接语音识别服务，请稍后重试。"), 0);
  }
  return readJsonResponse<TranscriptionResponse>(response);
}

export async function synthesizeSpeech(text: string, signal?: AbortSignal): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch("/api/digital-human/speech/syntheses", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
      signal,
    });
  } catch {
    if (signal?.aborted) {
      throw new DigitalHumanApiError(t("语音操作已中断。"), 0);
    }
    throw new DigitalHumanApiError(t("暂时无法连接语音合成服务，请稍后重试。"), 0);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw getResponseError(response, payload);
  }
  if (!response.headers.get("content-type")?.startsWith("audio/")) {
    throw new DigitalHumanApiError(t("语音服务未返回有效音频。"), response.status);
  }
  return response.blob();
}

async function readJsonResponse<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) throw getResponseError(response, payload);
  return payload as T;
}

function getResponseError(response: Response, payload: unknown): DigitalHumanApiError {
  const detail =
    payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
  const fallback =
    response.status === 401
      ? t("登录状态已失效，请刷新页面后重新登录。")
      : response.status === 413
        ? t("录音文件过大，请缩短录音后重试。")
        : response.status === 422
          ? t("语音内容或格式无效，请检查后重试。")
          : response.status === 503 || response.status >= 500
            ? t("数字人语音服务暂不可用，请稍后重试。")
            : t("数字人请求失败，请稍后重试。");
  return new DigitalHumanApiError(getSafeErrorDetail(detail, fallback), response.status);
}
