import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../../components/ToastProvider";
import { MembershipCheckoutPage } from "./MembershipCheckoutPage";
import { MembershipStatusProvider } from "./MembershipStatusContext";
import { getMembershipOverview, listMembershipPlans, listPaymentMethods } from "./membershipApi";

vi.mock("./membershipApi", () => ({
  getMembershipOverview: vi.fn(),
  listMembershipPlans: vi.fn(),
  listPaymentMethods: vi.fn(),
  getMembershipOrder: vi.fn(),
  createMembershipOrder: vi.fn(),
  createCheckoutSession: vi.fn(),
}));

afterEach(cleanup);

describe("MembershipCheckoutPage", () => {
  it("uses the selected plan and available payment methods from the API", async () => {
    vi.mocked(getMembershipOverview).mockResolvedValue({
      active_period: null,
      upcoming_periods: [],
      latest_expired_period: null,
    });
    vi.mocked(listMembershipPlans).mockResolvedValue([
      { id: "501", name: "服务端套餐名称", price: "56.78", duration_days: 45 },
    ]);
    vi.mocked(listPaymentMethods).mockResolvedValue([
      { code: "provider-x", name: "服务端支付渠道", description: "可用支付方式说明" },
    ]);

    render(
      <ToastProvider>
        <MembershipStatusProvider isGuest={false}>
          <MembershipCheckoutPage
            isGuest={false}
            onNavigate={vi.fn()}
            orderId={null}
            planId="501"
          />
        </MembershipStatusProvider>
      </ToastProvider>,
    );

    expect(await screen.findByText("OrionAI 会员 · 服务端套餐名称")).toBeInTheDocument();
    expect(screen.getByText("45 天")).toBeInTheDocument();
    expect(screen.getByText("¥56.78")).toBeInTheDocument();
    expect(screen.getByText("服务端支付渠道")).toBeInTheDocument();
    expect(screen.queryByText("Stripe 支付")).not.toBeInTheDocument();
  });
});
