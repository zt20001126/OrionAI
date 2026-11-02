export interface MembershipPlan {
  id: string;
  name: string;
  price: string;
  duration_days: number;
}

export interface MembershipPeriod {
  order_id: string;
  plan_id: string;
  plan_name: string;
  starts_at: string;
  expires_at: string;
}

export interface MembershipOverview {
  active_period: MembershipPeriod | null;
  upcoming_periods: MembershipPeriod[];
  latest_expired_period: MembershipPeriod | null;
}

export type MembershipOrderStatus = "pending" | "paid" | "failed" | "expired";
export type MembershipOrderType = "purchase" | "manual_grant";

export interface MembershipOrder {
  order_id: string;
  plan_id: string;
  plan_name: string;
  amount: string;
  order_type: MembershipOrderType;
  duration_days: number;
  status: MembershipOrderStatus;
  created_at: string;
  paid_at: string | null;
}

export interface MembershipOrderPage {
  items: MembershipOrder[];
  total: number;
  page: number;
  page_size: number;
}

export interface PaymentMethod {
  code: string;
  name: string;
  description: string | null;
}

export interface CreateMembershipOrderResponse {
  order_id: string;
  status: MembershipOrderStatus;
  amount: string;
  order_type: MembershipOrderType;
  duration_days: number;
  created_at: string;
}

export interface CheckoutSessionResponse {
  order_id: string;
  checkout_url: string;
  expires_at: string;
}
