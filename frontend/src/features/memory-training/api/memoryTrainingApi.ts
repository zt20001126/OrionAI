/** 记忆训练 REST API 与前端 DTO，集中维护接口路径和错误处理。 */

import { getSafeErrorDetail } from "../../../utils/safeErrorMessage";

export type TrainingState =
  | "image_loading"
  | "observing"
  | "waiting_questions"
  | "answering"
  | "completed"
  | "generation_failed";

export interface Preparation {
  tool_name: string;
  description: string;
  observation_seconds: number;
  question_count: number;
  score_per_question: number;
  max_score: number;
}

export interface CreatedTrainingSession {
  session_id: string;
  state: TrainingState;
  image_url: string;
}

export interface TrainingStatus {
  session_id: string;
  state: TrainingState;
  remaining_ms: number;
  questions_ready: boolean;
  image_url: string | null;
  error_code: string | null;
}

export interface PublicQuestion {
  id: string;
  prompt: string;
  options: Array<{ id: string; text: string }>;
}

export interface QuestionReview {
  id: string;
  prompt: string;
  user_option_id: string;
  user_option_text: string;
  correct_option_id: string;
  correct_option_text: string;
  is_correct: boolean;
  score: 0 | 20;
  explanation: string;
}

export interface TrainingResult {
  session_id: string;
  score: number;
  correct_count: number;
  incorrect_count: number;
  correct_rate: number;
  image_url: string;
  questions: QuestionReview[];
}

export class MemoryTrainingApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "MemoryTrainingApiError";
    this.status = status;
    this.code = code;
  }
}

async function requestMemoryTrainingApi<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "include", ...init });
  } catch {
    throw new Error("网络连接异常，请检查网络后重试。");
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const errorPayload = payload && typeof payload === "object" ? payload : null;
    const detail = errorPayload && "detail" in errorPayload ? errorPayload.detail : null;
    const code =
      errorPayload && "code" in errorPayload && typeof errorPayload.code === "string"
        ? errorPayload.code
        : null;
    const fallback =
      response.status === 401
        ? "登录状态已失效，请刷新页面后重新登录。"
        : response.status >= 500
          ? "记忆训练服务暂时不可用，请稍后重试。"
          : "训练状态已发生变化，请刷新后重试。";
    throw new MemoryTrainingApiError(
      getSafeErrorDetail(detail, fallback),
      response.status,
      code,
    );
  }
  return payload as T;
}

/** 获取不含图片的训练准备信息。 */
export function getTrainingPreparation(signal?: AbortSignal): Promise<Preparation> {
  return requestMemoryTrainingApi("/api/v1/memory-training/prepare", { signal });
}

/** 创建新会话并返回本次图片公开链接。 */
export function createTrainingSession(): Promise<CreatedTrainingSession> {
  return requestMemoryTrainingApi("/api/v1/memory-training/sessions", {
    method: "POST",
  });
}

/** 图片加载完成后启动服务器端观察计时。 */
export function startTrainingObservation(sessionId: string): Promise<{
  session_id: string;
  state: TrainingState;
  observation_started_at: string;
  observation_deadline_at: string;
  remaining_ms: number;
}> {
  return requestMemoryTrainingApi(
    `/api/v1/memory-training/sessions/${sessionId}/observation/start`,
    { method: "POST" },
  );
}

/** 查询会话服务端阶段和观察剩余时间。 */
export function getTrainingStatus(
  sessionId: string,
  signal?: AbortSignal,
): Promise<TrainingStatus> {
  return requestMemoryTrainingApi(`/api/v1/memory-training/sessions/${sessionId}`, { signal });
}

/** 仅在观察截止后读取不带答案的五道题目。 */
export async function getTrainingQuestions(
  sessionId: string,
  signal?: AbortSignal,
): Promise<PublicQuestion[]> {
  const response = await requestMemoryTrainingApi<{ questions: PublicQuestion[] }>(
    `/api/v1/memory-training/sessions/${sessionId}/questions`,
    { signal },
  );
  return response.questions;
}

/** 提交所有选择，由服务端判分。 */
export function submitTrainingAnswers(
  sessionId: string,
  answers: Record<string, string>,
): Promise<{ state: "completed"; score: number; correct_count: number; question_count: number }> {
  return requestMemoryTrainingApi(`/api/v1/memory-training/sessions/${sessionId}/answers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answers }),
  });
}

/** 获取已提交训练的成绩和逐题回顾。 */
export function getTrainingResult(
  sessionId: string,
  signal?: AbortSignal,
): Promise<TrainingResult> {
  return requestMemoryTrainingApi(
    `/api/v1/memory-training/sessions/${sessionId}/result`,
    { signal },
  );
}
