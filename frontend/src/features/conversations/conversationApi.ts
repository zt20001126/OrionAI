export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationSummary[];
  limit: number;
  offset: number;
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
  type: "SingleChoice";
  options: QuestionOption[];
  allow_custom_input: false;
}

export interface QuestionContentPart {
  type: "question";
  questions: SingleChoiceQuestion[];
}

export type MessageContentPart = TextContentPart | QuestionContentPart;

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: { parts: MessageContentPart[] };
  created_at: string;
}

export interface MessageListResponse {
  items: ConversationMessage[];
  limit: number;
  offset: number;
}

export interface AgentTurnResponse {
  status: "completed" | "waiting";
  message: ConversationMessage;
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
    const detail =
      payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    const message =
      typeof detail === "string"
        ? detail
        : response.status === 422
          ? "请检查填写内容是否正确。"
          : "请求失败，请稍后重试。";
    throw new ConversationApiError(message, response.status);
  }

  return payload as T;
}

export function createConversation(): Promise<ConversationSummary> {
  return request<ConversationSummary>("", undefined, "POST");
}

export function listConversations(offset = 0): Promise<ConversationListResponse> {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
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

export function submitQuestionAnswers(
  conversationId: string,
  answers: Record<string, string>,
): Promise<AgentTurnResponse> {
  return request<AgentTurnResponse>(`/${conversationId}/answers`, { answers });
}

export async function listAllMessages(conversationId: string): Promise<ConversationMessage[]> {
  const items: ConversationMessage[] = [];
  let offset = 0;

  while (true) {
    const page = await listMessages(conversationId, offset);
    items.push(...page.items);
    if (page.items.length < page.limit) return items;
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
