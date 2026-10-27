import type { ResumeDraft, ResumeResponse } from "./model/types";

const RESUME_API = "/api/resume";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { credentials: "include", ...init });
  } catch {
    throw new Error("暂时无法连接简历服务，请检查后端状态后重试。");
  }
  const payload: unknown = response.headers.get("content-type")?.includes("application/json")
    ? await response.json().catch(() => null)
    : null;
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    throw new Error(typeof detail === "string" ? detail : "简历请求失败，请稍后重试。");
  }
  return payload as T;
}

export function getResume(): Promise<ResumeResponse> {
  return request<ResumeResponse>(RESUME_API);
}

export function saveResume(
  draft: ResumeDraft,
  expectedUpdatedAt: string | null,
): Promise<ResumeResponse> {
  return request<ResumeResponse>(RESUME_API, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...draft, expected_updated_at: expectedUpdatedAt }),
  });
}

export async function uploadResumePhoto(file: File): Promise<{ photo_id: string }> {
  const data = new FormData();
  data.append("file", file);
  return request<{ photo_id: string }>(`${RESUME_API}/photo`, { method: "POST", body: data });
}

export function deleteStagedResumePhoto(photoId: string): Promise<{ deleted: boolean }> {
  return request(`${RESUME_API}/photo?photo_id=${encodeURIComponent(photoId)}`, {
    method: "DELETE",
  });
}

export async function downloadResumePdf(): Promise<void> {
  const response = await fetch(`${RESUME_API}/export/pdf`, { credentials: "include" });
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail =
      payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    throw new Error(typeof detail === "string" ? detail : "PDF 导出失败，请稍后重试。");
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = "resume.pdf";
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000);
}
