/** 集中定义问题反馈 API 请求与响应结构。 */

import { getSafeErrorDetail } from "../../utils/safeErrorMessage";

export interface FeedbackInput {
  title: string;
  content: string;
}

export interface FeedbackResponse {
  message: string;
}

/** 使用当前 Cookie 会话提交反馈，不接受前端提供的用户身份。 */
export async function submitFeedback(input: FeedbackInput): Promise<FeedbackResponse> {
  let response: Response;
  try {
    response = await fetch("/api/v1/feedback", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  } catch {
    throw new Error("网络连接异常，请检查网络后重试。");
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload.detail as unknown)
        : null;
    throw new Error(getErrorMessage(detail, response.status));
  }

  return payload as FeedbackResponse;
}

function getErrorMessage(detail: unknown, status: number): string {
  if (status === 401) return "登录状态已失效，请刷新页面后重新登录。";
  if (status === 429) return "提交过于频繁，请稍后重试。";
  if (status >= 500) return "反馈服务暂时不可用，请稍后重试。";
  return getSafeErrorDetail(detail, "反馈提交失败，请稍后重试。");
}
