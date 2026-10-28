import { getSafeErrorDetail } from "../../utils/safeErrorMessage";

export interface ConversationSummary {
  id: string;
  skill_code: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationSummary[];
  limit: number;
  offset: number;
  total_count: number;
}

export interface TextContentPart {
  type: "text";
  text: string;
}

export interface QuestionOption {
  label: string;
  description: string;
}

export interface SingleChoiceQuestion {
  id: string;
  title: string;
  context?: string | null;
  type: "SingleChoice";
  options: QuestionOption[];
  allow_custom_input: false;
}

export interface QuestionContentPart {
  type: "question";
  questions: SingleChoiceQuestion[];
}

export interface SubmittedQuestionAnswer {
  question_id: string;
  question: string;
  answer: string;
}

export interface QuestionAnswersContentPart {
  type: "question_answers";
  items: SubmittedQuestionAnswer[];
}

export interface ImageResultContentPart {
  type: "image_result";
  task_result_id: string;
  generation_status: "succeeded";
  image_url: string;
}

export type MessageContentPart =
  TextContentPart | QuestionContentPart | QuestionAnswersContentPart | ImageResultContentPart;

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: { parts: MessageContentPart[] };
  created_at: string;
}

export interface MessageListResponse {
  items: ConversationMessage[];
  skill_code: string;
  limit: number;
  offset: number;
}

export interface AgentTurnResponse {
  status: "completed" | "waiting";
  message: ConversationMessage;
}

export interface ConversationTextDeltaEvent {
  type: "text_delta";
  content: string;
}

export interface ConversationQuestionEvent {
  type: "question";
  message: ConversationMessage;
}

export type ConversationStreamMessageData = ConversationTextDeltaEvent | ConversationQuestionEvent;

interface ConversationStreamEnvelope {
  event_type: "start" | "message" | "heartbeat" | "end";
  data: unknown;
}

export class ConversationApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ConversationApiError";
  }
}

const PAGE_SIZE = 100;

async function request<T>(
  path: string,
  body?: object,
  method: "GET" | "POST" = body ? "POST" : "GET",
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/conversations${path}`, {
      method,
      credentials: "include",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ConversationApiError("暂时无法连接对话服务，请检查后端状态后重试。", 0);
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw getResponseError(response, payload);
  }

  return payload as T;
}

function getResponseError(response: Response, payload: unknown): ConversationApiError {
  const detail =
    payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
  const message = getUserFacingErrorMessage(detail, response.status);
  return new ConversationApiError(message, response.status);
}

function getUserFacingErrorMessage(detail: unknown, status: number): string {
  if (status === 401) return "登录状态已失效，请刷新页面后重新登录。";
  if (status === 404) return "会话不存在或无权访问，无法打开。";
  if (status === 409) return "当前会话正在等待题卡答案，请先完成题卡。";
  if (status === 422) return "请检查填写内容是否正确。";
  if (status === 503) return "对话服务暂不可用，请稍后重试。";
  if (status >= 500) return "对话服务暂不可用，请稍后重试。";
  return getSafeErrorDetail(detail, "请求失败，请稍后重试。");
}

export function createConversation(skillCode?: string): Promise<ConversationSummary> {
  return request<ConversationSummary>(
    "",
    skillCode ? { skill_code: skillCode } : undefined,
    "POST",
  );
}

export function listConversations(
  offset = 0,
  limit = PAGE_SIZE,
): Promise<ConversationListResponse> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return request<ConversationListResponse>(`?${query.toString()}`);
}

export function listMessages(conversationId: string, offset = 0): Promise<MessageListResponse> {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  return request<MessageListResponse>(`/${conversationId}/messages?${query.toString()}`);
}

export function sendConversationMessage(
  conversationId: string,
  message: string,
): Promise<AgentTurnResponse> {
  return request<AgentTurnResponse>(`/${conversationId}/messages`, { message });
}

export function streamConversationMessage(
  conversationId: string,
  message: string,
  onTextDelta: (content: string) => void,
  signal: AbortSignal,
): Promise<ConversationMessage | null> {
  return streamConversationTurn(
    `/${conversationId}/messages/stream`,
    { message },
    onTextDelta,
    signal,
  );
}

export function submitQuestionAnswers(
  conversationId: string,
  answers: Record<string, string>,
): Promise<AgentTurnResponse> {
  return request<AgentTurnResponse>(`/${conversationId}/answers`, { answers });
}

export function streamQuestionAnswers(
  conversationId: string,
  answers: Record<string, string>,
  onTextDelta: (content: string) => void,
  signal: AbortSignal,
): Promise<ConversationMessage | null> {
  return streamConversationTurn(
    `/${conversationId}/answers/stream`,
    { answers },
    onTextDelta,
    signal,
  );
}

async function streamConversationTurn(
  path: string,
  body: object,
  onTextDelta: (content: string) => void,
  signal: AbortSignal,
): Promise<ConversationMessage | null> {
  let response: Response;
  try {
    response = await fetch(`/api/conversations${path}`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    if (signal.aborted) throw new ConversationApiError("本次生成已中断。", 0);
    throw new ConversationApiError("暂时无法连接对话服务，请检查后端状态后重试。", 0);
  }

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw getResponseError(response, payload);
  }
  if (!response.headers.get("content-type")?.startsWith("text/event-stream") || !response.body) {
    throw new ConversationApiError("对话服务未返回有效的流式响应。", response.status);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let endStatus: string | null = null;
  let questionMessage: ConversationMessage | null = null;

  function consumeFrame(frame: string): void {
    const data = frame
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(line.startsWith("data: ") ? 6 : 5));
    if (data.length === 0) return;

    let event: ConversationStreamEnvelope;
    try {
      event = JSON.parse(data.join("\n")) as ConversationStreamEnvelope;
    } catch {
      throw new ConversationApiError("对话服务返回了无法读取的流式数据。", response.status);
    }

    if (event.event_type === "message" && event.data && typeof event.data === "object") {
      const messageData = event.data as Record<string, unknown>;
      if (messageData.type === "text_delta" && typeof messageData.content === "string") {
        onTextDelta(messageData.content);
      } else if (messageData.type === "question" && messageData.message) {
        questionMessage = messageData.message as ConversationMessage;
      }
    } else if (event.event_type === "end" && event.data && typeof event.data === "object") {
      const endData = event.data as Record<string, unknown>;
      endStatus = typeof endData.status === "string" ? endData.status : "failed";
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let delimiter = /\r\n\r\n|\n\n|\r\r/.exec(buffer);
      while (delimiter && delimiter.index !== undefined) {
        consumeFrame(buffer.slice(0, delimiter.index));
        buffer = buffer.slice(delimiter.index + delimiter[0].length);
        delimiter = /\r\n\r\n|\n\n|\r\r/.exec(buffer);
      }

      if (done) break;
    }

    if (buffer.trim()) consumeFrame(buffer);
  } catch (error) {
    if (signal.aborted) throw new ConversationApiError("本次生成已中断。", 0);
    if (error instanceof ConversationApiError) throw error;
    throw new ConversationApiError("读取对话流时连接中断，请重新加载会话后再试。", 0);
  } finally {
    reader.releaseLock();
  }

  if (endStatus !== "completed") {
    throw new ConversationApiError(
      endStatus === "failed"
        ? "助手生成中断，部分内容尚未保存；请检查会话后再决定是否重试。"
        : "对话连接已结束，但没有收到完整的结束事件。",
      0,
    );
  }
  return questionMessage;
}

export async function listAllMessages(conversationId: string): Promise<MessageListResponse> {
  const items: ConversationMessage[] = [];
  let offset = 0;

  while (true) {
    const page = await listMessages(conversationId, offset);
    items.push(...page.items);
    if (page.items.length < page.limit) {
      return { items, skill_code: page.skill_code, limit: page.limit, offset: 0 };
    }
    offset += page.items.length;
  }
}

export function getConversationErrorMessage(error: unknown): string {
  if (!(error instanceof ConversationApiError)) {
    return "请求失败，请稍后重试。";
  }

  if (error.status === 401) return "登录状态已失效，请刷新页面后重新登录。";
  if (error.status === 404) return "会话不存在或无权访问，无法打开。";
  if (error.status === 409) return "当前会话正在等待题卡答案，请先完成题卡。";
  if (error.status === 503) return error.message || "对话服务暂不可用，请稍后重试。";
  return error.message;
}
