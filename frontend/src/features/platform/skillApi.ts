/** 技能市场 API 类型与请求封装，统一管理接口地址和认证 Cookie。 */

import { getSafeErrorDetail } from "../../utils/safeErrorMessage";

export type SkillType = "agent" | "tool";
export type SkillStatus = "published" | "disabled";

/** 后端技能市场返回的技能信息。 */
export interface MarketSkill {
  /** Snowflake 技能 ID，以十进制字符串传输。 */
  id: string;
  /** 稳定的技能代码。 */
  code: string;
  /** 技能名称。 */
  name: string;
  /** 技能说明。 */
  description: string | null;
  /** 技能类型。 */
  type: SkillType;
  /** 技能发布状态。 */
  status: SkillStatus;
  /** 技能创建时间。 */
  created_at: string;
  /** 当前用户是否已添加此技能。 */
  is_added: boolean;
}

/** 当前用户已添加的技能及其关联时间。 */
export interface MySkill extends MarketSkill {
  /** 添加到当前用户技能列表的时间。 */
  added_at: string;
}

interface SkillPageResponse {
  /** 当前页技能。 */
  items: MarketSkill[];
  /** 符合条件的技能总数。 */
  total: number;
  /** 当前页码。 */
  page: number;
  /** 每页数量。 */
  page_size: number;
}

const SKILL_MARKET_PAGE_SIZE = 100;

function isSkillPageResponse(payload: unknown): payload is SkillPageResponse {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "items" in payload &&
    Array.isArray(payload.items) &&
    "total" in payload &&
    typeof payload.total === "number" &&
    "page" in payload &&
    typeof payload.page === "number" &&
    "page_size" in payload &&
    typeof payload.page_size === "number"
  );
}

async function requestSkillApi<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "include",
      ...init,
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
    throw new Error(getUserFacingErrorMessage(detail, response.status));
  }

  return payload as T;
}

function getUserFacingErrorMessage(detail: unknown, status: number): string {
  if (status === 401) return "登录状态已失效，请刷新页面后重新登录。";
  if (status === 422) return "请检查填写内容是否正确。";
  if (status >= 500) return "技能服务暂时不可用，请稍后重试。";
  return getSafeErrorDetail(detail, "技能请求失败，请稍后重试。");
}

/** 查询全部技能目录，逐页读取并包含停用技能。 */
export async function listMarketSkills(signal?: AbortSignal): Promise<MarketSkill[]> {
  const skills: MarketSkill[] = [];
  let page = 1;
  let total = Number.POSITIVE_INFINITY;

  while (skills.length < total) {
    const query = new URLSearchParams({
      include_disabled: "true",
      page: String(page),
      page_size: String(SKILL_MARKET_PAGE_SIZE),
    });
    const response = await requestSkillApi<unknown>(`/api/v1/skills?${query}`, { signal });
    if (!isSkillPageResponse(response)) {
      throw new Error("技能列表响应格式无效，请稍后重试。");
    }

    skills.push(...response.items);
    total = response.total;
    if (response.items.length === 0) break;
    page += 1;
  }

  return skills;
}

/** 查询当前用户已经添加且可用的技能。 */
export async function listMySkills(signal?: AbortSignal): Promise<MySkill[]> {
  const response = await requestSkillApi<{ items: MySkill[] }>("/api/v1/users/me/skills", {
    signal,
  });
  return response.items;
}

/** 将已发布技能添加到当前用户的技能列表。 */
export function addSkillToMySkills(skillId: string): Promise<MarketSkill> {
  return requestSkillApi<MarketSkill>("/api/v1/users/me/skills", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ skill_id: skillId }),
  });
}

/** 移除当前用户与技能的关联。 */
export async function removeSkillFromMySkills(skillId: string): Promise<void> {
  await requestSkillApi<void>(`/api/v1/users/me/skills/${skillId}`, { method: "DELETE" });
}
