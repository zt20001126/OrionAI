import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MembershipEntry } from "./MembershipEntry";
import { MembershipStatusProvider } from "./MembershipStatusContext";
import { getMembershipOverview } from "./membershipApi";

vi.mock("./membershipApi", () => ({
  getMembershipOverview: vi.fn(),
}));

afterEach(cleanup);

describe("MembershipEntry", () => {
  it("shows the active label and opens the membership center", async () => {
    vi.mocked(getMembershipOverview).mockResolvedValue({
      active_period: {
        order_id: "1",
        plan_id: "2",
        plan_name: "后端套餐",
        starts_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 86400000).toISOString(),
      },
      upcoming_periods: [],
      latest_expired_period: null,
    });
    const onNavigate = vi.fn();

    render(
      <MembershipStatusProvider isGuest={false}>
        <MembershipEntry onNavigate={onNavigate} />
      </MembershipStatusProvider>,
    );

    const entry = await screen.findByRole("button", { name: "VIP 会员" });
    fireEvent.click(entry);
    expect(onNavigate).toHaveBeenCalledWith("/membership");
  });

  it("uses the guest account state without inventing a member record", async () => {
    const onNavigate = vi.fn();
    render(
      <MembershipStatusProvider isGuest>
        <MembershipEntry onNavigate={onNavigate} />
      </MembershipStatusProvider>,
    );

    expect(await screen.findByRole("button", { name: "开通会员" })).toBeInTheDocument();
    expect(getMembershipOverview).not.toHaveBeenCalled();
  });
});
