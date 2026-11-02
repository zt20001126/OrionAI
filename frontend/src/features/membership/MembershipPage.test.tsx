import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ToastProvider";
import { MembershipPage } from "./MembershipPage";
import { MembershipStatusProvider } from "./MembershipStatusContext";
import { getMembershipOverview, listMembershipOrders, listMembershipPlans } from "./membershipApi";
import type { MembershipOverview, MembershipOrder, MembershipPlan } from "./types";

vi.mock("./membershipApi", () => ({
  getMembershipOverview: vi.fn(),
  getMembershipOrder: vi.fn(),
  listMembershipOrders: vi.fn(),
  listMembershipPlans: vi.fn(),
}));

afterEach(cleanup);

const plans: MembershipPlan[] = [
  { id: "101", name: "基础月卡", price: "12.30", duration_days: 30 },
  { id: "102", name: "标准季卡", price: "45.60", duration_days: 90 },
  { id: "103", name: "长期年卡", price: "78.90", duration_days: 365 },
];

const orders: MembershipOrder[] = [
  {
    order_id: "9001",
    plan_id: "102",
    plan_name: "标准季卡",
    amount: "45.60",
    order_type: "purchase",
    duration_days: 90,
    status: "paid",
    created_at: "2026-10-01T10:00:00Z",
    paid_at: "2026-10-01T10:01:00Z",
  },
];

function renderPage(overview: MembershipOverview) {
  const onNavigate = vi.fn();
  vi.mocked(getMembershipOverview).mockResolvedValue(overview);
  vi.mocked(listMembershipPlans).mockResolvedValue(plans);
  vi.mocked(listMembershipOrders).mockResolvedValue({
    items: orders,
    total: orders.length,
    page: 1,
    page_size: 5,
  });

  render(
    <ToastProvider>
      <MembershipStatusProvider isGuest={false}>
        <MembershipPage isGuest={false} onNavigate={onNavigate} />
      </MembershipStatusProvider>
    </ToastProvider>,
  );
  return { onNavigate };
}

describe("MembershipPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders plans, membership and recent orders from API responses", async () => {
    const expiresAt = new Date(Date.now() + 40 * 24 * 60 * 60 * 1000).toISOString();
    const { onNavigate } = renderPage({
      active_period: {
        order_id: "9001",
        plan_id: "102",
        plan_name: "标准季卡",
        starts_at: new Date().toISOString(),
        expires_at: expiresAt,
      },
      upcoming_periods: [],
      latest_expired_period: null,
    });

    expect(await screen.findByRole("heading", { name: "OrionAI 会员" })).toBeInTheDocument();
    expect(screen.getAllByText("标准季卡").length).toBeGreaterThan(0);
    expect(screen.getAllByText("¥45.60").length).toBeGreaterThan(0);
    expect(screen.getByText("12.30")).toBeInTheDocument();
    expect(screen.getByText("78.90")).toBeInTheDocument();
    expect(screen.getByText("推荐")).toBeInTheDocument();
    expect(screen.getByText("已支付")).toBeInTheDocument();

    const monthlyPlan = screen.getByRole("heading", { name: "基础月卡" }).closest("article");
    expect(monthlyPlan).not.toBeNull();
    fireEvent.click(within(monthlyPlan as HTMLElement).getByRole("button", { name: /立即开通/ }));
    expect(onNavigate).toHaveBeenCalledWith("/membership/checkout/101");
  });

  it("shows the expired state from the latest expired period", async () => {
    renderPage({
      active_period: null,
      upcoming_periods: [],
      latest_expired_period: {
        order_id: "9001",
        plan_id: "102",
        plan_name: "标准季卡",
        starts_at: "2026-06-01T00:00:00Z",
        expires_at: "2026-07-01T00:00:00Z",
      },
    });

    expect(await screen.findByRole("heading", { name: "会员已过期" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新开通" })).toBeInTheDocument();
    expect(screen.getAllByText("标准季卡").length).toBeGreaterThan(0);
  });
});
