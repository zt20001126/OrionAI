import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("shows the sidebar label and keeps navigating to the membership center", () => {
    const onNavigate = vi.fn();

    render(
      <MembershipStatusProvider isGuest>
        <MembershipEntry onNavigate={onNavigate} variant="sidebar" />
      </MembershipStatusProvider>,
    );

    const entry = screen.getByRole("button", { name: "会员中心" });
    expect(entry).toHaveAttribute("data-tooltip", "会员中心");
    fireEvent.click(entry);
    expect(onNavigate).toHaveBeenCalledWith("/membership");
  });

  it("uses the active period for the sidebar crown and turns it gray at expiry", async () => {
    const activeOverview = {
      active_period: {
        order_id: "1",
        plan_id: "2",
        plan_name: "后端套餐",
        starts_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 800).toISOString(),
      },
      upcoming_periods: [],
      latest_expired_period: null,
    };
    vi.mocked(getMembershipOverview).mockResolvedValueOnce(activeOverview).mockResolvedValueOnce({
      active_period: null,
      upcoming_periods: [],
      latest_expired_period: activeOverview.active_period,
    });

    render(
      <MembershipStatusProvider isGuest={false}>
        <MembershipEntry onNavigate={vi.fn()} variant="sidebar" />
      </MembershipStatusProvider>,
    );

    const entry = await screen.findByRole("button", { name: "会员中心" });
    await waitFor(() => expect(entry).toHaveClass("is-member"));
    await waitFor(() => expect(entry).not.toHaveClass("is-member"), { timeout: 1500 });
    expect(getMembershipOverview).toHaveBeenCalledTimes(2);
  });

  it("keeps the sidebar crown gray when only an expired period exists", async () => {
    vi.mocked(getMembershipOverview).mockResolvedValue({
      active_period: null,
      upcoming_periods: [],
      latest_expired_period: {
        order_id: "1",
        plan_id: "2",
        plan_name: "后端套餐",
        starts_at: new Date(Date.now() - 172800000).toISOString(),
        expires_at: new Date(Date.now() - 86400000).toISOString(),
      },
    });

    render(
      <MembershipStatusProvider isGuest={false}>
        <MembershipEntry onNavigate={vi.fn()} variant="sidebar" />
      </MembershipStatusProvider>,
    );

    const entry = await screen.findByRole("button", { name: "会员中心" });
    expect(entry).not.toHaveClass("is-member");
  });
});
