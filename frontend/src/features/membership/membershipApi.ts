import { getSafeErrorDetail } from "../../utils/safeErrorMessage";
import type {
  CheckoutSessionResponse,
  CreateMembershipOrderResponse,
  MembershipOrder,
  MembershipOrderPage,
  MembershipOverview,
  MembershipPlan,
  PaymentMethod,
} from "./types";

export class MembershipApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "MembershipApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      credentials: "include",
      ...init,
    });
  } catch {
    throw new MembershipApiError("网络连接异常，请检查网络后重试。", 0);
  }

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload.detail as unknown)
        : null;
    const fallback =
      response.status === 401
        ? "登录状态已失效，请刷新页面后重新登录。"
        : response.status >= 500
          ? "会员服务暂时不可用，请稍后重试。"
          : "请求失败，请稍后重试。";
    throw new MembershipApiError(getSafeErrorDetail(detail, fallback), response.status);
  }

  return payload as T;
}

export function listMembershipPlans(signal?: AbortSignal): Promise<MembershipPlan[]> {
  return request<MembershipPlan[]>("/api/v1/membership/plans", { signal });
}

export function getMembershipOverview(signal?: AbortSignal): Promise<MembershipOverview> {
  return request<MembershipOverview>("/api/v1/users/me/membership", { signal });
}

/** 每次技能使用前从服务端读取 Redis 缓存的会员准入结果。 */
export async function checkMembershipAccess(signal?: AbortSignal): Promise<boolean> {
  const response = await request<unknown>("/api/v1/users/me/membership/access", { signal });
  if (
    typeof response !== "object" ||
    response === null ||
    !("is_member" in response) ||
    typeof response.is_member !== "boolean"
  ) {
    throw new MembershipApiError("会员状态响应无效，请稍后重试。", 0);
  }
  return response.is_member;
}

export function listMembershipOrders(
  page: number,
  pageSize: number,
  signal?: AbortSignal,
): Promise<MembershipOrderPage> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  return request<MembershipOrderPage>("/api/v1/users/me/membership/orders?" + query, { signal });
}

export function getMembershipOrder(
  orderId: string,
  signal?: AbortSignal,
): Promise<MembershipOrder> {
  return request<MembershipOrder>("/api/v1/membership/orders/" + encodeURIComponent(orderId), {
    signal,
  });
}

export function createMembershipOrder(
  planId: string,
  requestId: string,
): Promise<CreateMembershipOrderResponse> {
  return request<CreateMembershipOrderResponse>("/api/v1/membership/orders", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ plan_id: planId, request_id: requestId }),
  });
}

export function listPaymentMethods(signal?: AbortSignal): Promise<PaymentMethod[]> {
  return request<PaymentMethod[]>("/api/v1/payments/methods", { signal });
}

export function createCheckoutSession(
  orderId: string,
  paymentMethod: string,
): Promise<CheckoutSessionResponse> {
  return request<CheckoutSessionResponse>("/api/v1/payments/checkout-sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order_id: orderId, payment_method: paymentMethod }),
  });
}
