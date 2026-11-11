import { getSafeErrorDetail } from "../../utils/safeErrorMessage";
import { t } from "../../i18n/localeStore";

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
  questions: Question[];
}

export interface TextQuestion {
  id: string;
  title: string;
  type: "Text";
}

export type Question = SingleChoiceQuestion | TextQuestion;

export interface SubmittedQuestionAnswer {
  question_id: string;
  question: string;
  answer: string;
}

export type UserLocationContext =
  | {
      status: "granted";
      latitude: number;
      longitude: number;
      accuracy_meters: number;
    }
  | { status: "denied" | "unavailable" };

export const DIGITAL_HUMAN_LOCATION_CONSENT_QUESTION_ID = "digital_human_location_consent";
export const DIGITAL_HUMAN_LOCATION_CONSENT_ALLOW_ANSWER = "允许获取当前位置";

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

export interface VideoResultContentPart {
  type: "video_result";
  task_result_id: string;
  generation_status: "succeeded";
  video_url: string;
}

export interface KlineCandle {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number | null;
}

export interface KlineMovingAverage {
  period: 5 | 10 | 20 | 60;
  values: (number | null)[];
}

export interface KlineChartPayload {
  code: string;
  name: string;
  period: "daily" | "weekly" | "monthly";
  adjust: "qfq";
  start_date: string;
  end_date: string;
  source: string;
  candles: KlineCandle[];
  moving_averages?: KlineMovingAverage[];
}

export interface KlineChartContentPart {
  type: "kline_chart";
  content: KlineChartPayload;
}

export interface PlaceCard {
  id: string;
  name: string;
  address: string;
  distance: number;
  tel: string | null;
  business_hours: string | null;
  rating: number | null;
}

export interface PlaceCardsPayload {
  title: string;
  total: number;
  places: PlaceCard[];
}

export interface PlaceCardsContentPart {
  type: "place_cards";
  data: PlaceCardsPayload;
}

export type MessageContentPart =
  | TextContentPart
  | QuestionContentPart
  | QuestionAnswersContentPart
  | ImageResultContentPart
  | VideoResultContentPart
  | KlineChartContentPart
  | PlaceCardsContentPart;

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

export interface ConversationRunResponse {
  run_id: string;
}

export interface ConversationTextDeltaEvent {
  type: "text_delta";
  content: string;
}

export interface ConversationQuestionEvent {
  type: "question";
  message: ConversationMessage;
}

export interface ConversationKlineChartEvent {
  type: "kline_chart";
  content: KlineChartPayload;
}

export interface ConversationPlaceCardsEvent {
  type: "place_cards";
  data: PlaceCardsPayload;
}

export type ConversationStreamMessageData =
  | ConversationTextDeltaEvent
  | ConversationQuestionEvent
  | ConversationKlineChartEvent
  | ConversationPlaceCardsEvent;

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
  idempotencyKey?: string,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/conversations${path}`, {
      method,
      credentials: "include",
      headers: {
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ConversationApiError(t("暂时无法连接对话服务，请检查后端状态后重试。"), 0);
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
  if (status === 401) return t("登录状态已失效，请刷新页面后重新登录。");
  if (status === 404) return t("会话不存在或无权访问，无法打开。");
  if (status === 409) {
    if (typeof detail === "string" && /幂等键|本次发送|相同消息/.test(detail)) {
      return getSafeErrorDetail(detail, t("消息发送冲突，请稍后重试。"));
    }
    return t("当前会话正在等待题卡答案，请先完成题卡。");
  }
  if (status === 422) return t("请检查填写内容是否正确。");
  if (status === 503) return t("对话服务暂不可用，请稍后重试。");
  if (status >= 500) return t("对话服务暂不可用，请稍后重试。");
  return getSafeErrorDetail(detail, t("请求失败，请稍后重试。"));
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
  idempotencyKey?: string,
): Promise<ConversationMessage | null> {
  return streamConversationRun(
    conversationId,
    () => startConversationMessageRun(conversationId, message, idempotencyKey),
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
  return streamConversationRun(
    conversationId,
    () => startQuestionAnswersRun(conversationId, answers),
    onTextDelta,
    signal,
  );
}

/** 兼容旧调用方，同时将浏览器请求改为独立任务加监听的两阶段流程。 */
async function streamConversationRun(
  conversationId: string,
  start: () => Promise<ConversationRunResponse>,
  onTextDelta: (content: string) => void,
  signal: AbortSignal,
): Promise<ConversationMessage | null> {
  const { run_id: runId } = await start();
  let status: string | null = null;
  let questionMessage: ConversationMessage | null = null;
  await listenConversationRun(
    conversationId,
    runId,
    onTextDelta,
    (message) => {
      questionMessage = message;
    },
    (nextStatus) => {
      status = nextStatus;
    },
    signal,
  );
  if (signal.aborted) return null;
  if (status === "completed") return questionMessage;
  if (status === "interrupted") {
    throw new ConversationApiError(t("本次回复已中断，已保留生成内容。"), 0);
  }
  throw new ConversationApiError(t("对话连接已结束，但没有收到完整的结束事件。"), 0);
}

/** 创建后台消息生成任务；输入为会话和消息，输出 Redis 管理的 run_id。 */
export function startConversationMessageRun(
  conversationId: string,
  message: string,
  idempotencyKey?: string,
): Promise<ConversationRunResponse> {
  return request<ConversationRunResponse>(
    `/${conversationId}/runs/messages`,
    { message },
    "POST",
    idempotencyKey,
  );
}

/** 提交题卡答案并创建后台任务；输入可选数字人本轮定位结果；调用方：对话题卡。 */
export function startQuestionAnswersRun(
  conversationId: string,
  answers: Record<string, string>,
  location?: UserLocationContext,
): Promise<ConversationRunResponse> {
  return request<ConversationRunResponse>(`/${conversationId}/runs/answers`, {
    answers,
    ...(location ? { location } : {}),
  });
}

/** 查询会话活动任务；无活动任务时返回 null。 */
export function getActiveConversationRun(
  conversationId: string,
): Promise<ConversationRunResponse | null> {
  return request<ConversationRunResponse | null>(`/${conversationId}/runs/active`);
}

/** 主动停止本轮生成；关闭 listen 的 AbortSignal 不会调用此接口。 */
export function interruptConversationRun(conversationId: string, runId: string): Promise<void> {
  return request<void>(`/${conversationId}/runs/${runId}/interrupt`, {}, "POST");
}

/** 监听 Redis 回放流；重连时服务端会从首个事件回放，不会重启 Agent。 */
export async function listenConversationRun(
  conversationId: string,
  runId: string,
  onTextDelta: (content: string) => void,
  onQuestion: (message: ConversationMessage) => void,
  onStatus: (status: string) => void,
  signal: AbortSignal,
  onKlineChart?: (chart: KlineChartPayload) => void,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/conversations/${conversationId}/runs/${runId}/listen`, {
      credentials: "include",
      signal,
    });
  } catch {
    if (signal.aborted) return;
    throw new ConversationApiError(t("暂时无法连接对话服务，请检查后端状态后重试。"), 0);
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    throw getResponseError(response, payload);
  }
  if (!response.body)
    throw new ConversationApiError(t("对话服务未返回有效的流式响应。"), response.status);

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  const consumeFrame = (frame: string) => {
    const raw = frame
      .split(/\r?\n/)
      .find((line) => line.startsWith("data:"))
      ?.slice(5)
      .trim();
    if (!raw) return;
    const envelope = JSON.parse(raw) as ConversationStreamEnvelope;
    if (!envelope.data || typeof envelope.data !== "object") return;
    const event = envelope.data as Record<string, unknown>;
    if (envelope.event_type !== "message") return;
    if (event.type === "text_delta" && typeof event.content === "string")
      onTextDelta(event.content);
    if (event.type === "question" && event.message)
      onQuestion(event.message as ConversationMessage);
    if (event.type === "kline_chart" && event.content && onKlineChart)
      onKlineChart(event.content as KlineChartPayload);
    if (event.type === "run_status" && typeof event.status === "string") onStatus(event.status);
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let delimiter = /\r\n\r\n|\n\n|\r\r/.exec(buffer);
      while (delimiter?.index !== undefined) {
        consumeFrame(buffer.slice(0, delimiter.index));
        buffer = buffer.slice(delimiter.index + delimiter[0].length);
        delimiter = /\r\n\r\n|\n\n|\r\r/.exec(buffer);
      }
      if (done) break;
    }
    if (buffer.trim()) consumeFrame(buffer);
  } catch (error) {
    if (signal.aborted) return;
    if (error instanceof ConversationApiError) throw error;
    throw new ConversationApiError(t("读取对话流时连接中断，请重新加载会话后再试。"), 0);
  } finally {
    reader.releaseLock();
  }
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
    return t("请求失败，请稍后重试。");
  }

  if (error.status === 401) return t("登录状态已失效，请刷新页面后重新登录。");
  if (error.status === 404) return t("会话不存在或无权访问，无法打开。");
  if (error.status === 409) {
    if (/幂等键|本次发送|相同消息/.test(error.message)) return error.message;
    return t("当前会话正在等待题卡答案，请先完成题卡。");
  }
  if (error.status === 503) return error.message || t("对话服务暂不可用，请稍后重试。");
  return error.message;
}

export interface DigitalHumanAudioEvent {
  type: "audio_segment" | "audio_done" | "audio_error";
  turn_id: string;
  segment_id?: number;
  audio?: string;
}

/** 读取数字人回复流；输入会话、请求内容和播报状态，输出文字与有序音频事件；调用方：数字人页面。 */
export async function streamDigitalHumanReply(
  conversationId: string,
  endpoint: "messages" | "answers",
  body: object,
  onText: (text: string) => void,
  onAudio: (event: DigitalHumanAudioEvent) => void | Promise<void>,
  signal: AbortSignal,
  idempotencyKey?: string,
  onKlineChart?: (chart: KlineChartPayload) => void,
  voiceEnabled = true,
  onPlaceCards?: (cards: PlaceCardsPayload) => void,
): Promise<void> {
  const response = await fetch(
    `/api/conversations/${conversationId}/${endpoint}/stream?voice=${voiceEnabled}`,
    {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      },
      body: JSON.stringify(body),
      signal,
    },
  );
  if (!response.ok || !response.body) {
    const payload: unknown = await response.json().catch(() => null);
    throw getResponseError(response, payload);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  const consume = async (frame: string) => {
    if (signal.aborted) return;
    const raw = frame
      .split(/\r?\n/)
      .find((line) => line.startsWith("data:"))
      ?.slice(5)
      .trim();
    if (!raw) return;
    const envelope = JSON.parse(raw) as ConversationStreamEnvelope;
    if (!envelope.data || typeof envelope.data !== "object") return;
    const event = envelope.data as Record<string, unknown>;
    if (envelope.event_type === "end") {
      completed = event.status === "completed";
    } else if (envelope.event_type === "message") {
      if (event.type === "text_delta" && typeof event.content === "string") onText(event.content);
      if (event.type === "kline_chart" && event.content && onKlineChart)
        onKlineChart(event.content as KlineChartPayload);
      if (event.type === "place_cards" && event.data && onPlaceCards)
        onPlaceCards(event.data as PlaceCardsPayload);
      if (
        (event.type === "audio_segment" ||
          event.type === "audio_done" ||
          event.type === "audio_error") &&
        typeof event.turn_id === "string"
      ) {
        await onAudio(event as unknown as DigitalHumanAudioEvent);
      }
    }
  };
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let delimiter = /\r\n\r\n|\n\n|\r\r/.exec(buffer);
      while (delimiter?.index !== undefined) {
        await consume(buffer.slice(0, delimiter.index));
        buffer = buffer.slice(delimiter.index + delimiter[0].length);
        delimiter = /\r\n\r\n|\n\n|\r\r/.exec(buffer);
      }
      if (done || signal.aborted) break;
    }
    if (buffer.trim() && !signal.aborted) await consume(buffer);
    if (!completed && !signal.aborted) throw new ConversationApiError(t("对话连接已中断。"), 0);
  } finally {
    if (signal.aborted) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
