import { getSafeErrorDetail } from "../../../utils/safeErrorMessage";

export interface TourismSummary {
  rules_count: number;
  comments_count: number;
  analyzed_count: number;
  rules_ready: boolean;
}

export interface TourismComment {
  id: string;
  source_type: string;
  nickname: string | null;
  ugc_type: string | null;
  platform: string | null;
  title: string | null;
  content: string;
  published_at: string | null;
  analyzed: boolean;
}

export interface TourismCommentPage {
  items: TourismComment[];
  limit: number;
  offset: number;
  total_count: number;
}

export interface TourismImportResponse {
  imported_count: number;
  skipped_count: number;
  failed_count: number;
  errors: string[];
}

export interface TourismMatch {
  status: "matched" | "review" | "unmatched";
  evidence: string | null;
  reason: string | null;
  rule: {
    id: string;
    major_item: string;
    minor_item: string;
    indicator_code: string;
    indicator_name: string;
    subitem_number: string;
    subitem_name: string;
    scoring_criterion: string;
    description: string | null;
    data_source_detail: string | null;
  } | null;
}

export interface TourismResultGroup {
  comment: TourismComment;
  matches: TourismMatch[];
}

export interface TourismResults {
  items: TourismResultGroup[];
  limit: number;
  offset: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/tourism-insight${path}`, { credentials: "include", ...init });
  } catch {
    throw new Error("暂时无法连接文旅洞察服务，请检查后端状态后重试。");
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    throw new Error(getSafeErrorDetail(detail, "文旅洞察请求失败，请稍后重试。"));
  }
  return payload as T;
}

export function getTourismSummary(): Promise<TourismSummary> {
  return request("/summary");
}

export function listTourismComments(offset = 0): Promise<TourismCommentPage> {
  return request(`/comments?limit=20&offset=${offset}`);
}

export function listTourismResults(offset = 0): Promise<TourismResults> {
  return request(`/results?limit=20&offset=${offset}`);
}

export function uploadTourismFile(
  kind: "rules" | "comments",
  file: File,
  options: { replace?: boolean; limit?: number } = {},
): Promise<TourismImportResponse> {
  const body = new FormData();
  body.append("file", file);
  if (kind === "rules") body.append("replace", String(options.replace ?? false));
  if (kind === "comments") body.append("limit", String(options.limit ?? 50));
  return request(`/${kind}/import`, { method: "POST", body });
}

export function analyzeTourismComments(commentIds: string[]): Promise<{
  items: Array<{ comment_id: string; status: "completed" | "failed"; message: string }>;
}> {
  return request("/analyses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment_ids: commentIds }),
  });
}
