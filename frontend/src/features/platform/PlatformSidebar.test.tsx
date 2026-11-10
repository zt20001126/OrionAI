import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PlatformSidebar } from "./PlatformSidebar";
import { navigationItems, platformPaths, type PlatformRoute } from "./platformData";

vi.mock("../auth/ProductIntro", () => ({ BrandMark: () => null }));
vi.mock("../membership/MembershipEntry", () => ({ MembershipEntry: () => null }));
vi.mock("../notifications/NotificationBell", () => ({ NotificationBell: () => null }));
vi.mock("./ProfileMenu", () => ({ ProfileMenu: () => null }));

afterEach(cleanup);

function renderSidebar(pathname: PlatformRoute, onNavigate = vi.fn()) {
  render(
    <PlatformSidebar
      account="user@example.com"
      isLoggingOut={false}
      onLogout={vi.fn()}
      onNavigate={onNavigate}
      pathname={pathname}
      collapsed={false}
      onToggleCollapsed={vi.fn()}
    />,
  );

  return onNavigate;
}

describe("PlatformSidebar", () => {
  it("places Orion Assistant between My Skills and Conversations", () => {
    expect(navigationItems.map(({ path }) => path)).toEqual([
      platformPaths.market,
      platformPaths.mySkills,
      platformPaths.digitalHuman,
      platformPaths.sessions,
    ]);
  });

  it("selects the digital human item for a conversation route and navigates to its root", () => {
    const onNavigate = renderSidebar(`${platformPaths.digitalHuman}/42`);
    const navigation = screen.getByRole("navigation");
    const item = within(navigation).getByRole("link", { name: "Orion 助手" });

    expect(item).toHaveAttribute("aria-current", "page");
    fireEvent.click(item);
    expect(onNavigate).toHaveBeenCalledWith(platformPaths.digitalHuman);
  });

  it("navigates the brand to Orion Assistant without navigating again on that route", () => {
    const onNavigate = renderSidebar(platformPaths.market);
    const brand = screen.getByRole("link", { name: "前往 Orion 助手" });

    fireEvent.click(brand);
    expect(onNavigate).toHaveBeenCalledWith(platformPaths.digitalHuman);
  });

  it("does not navigate again when the brand is clicked inside an assistant conversation", () => {
    const onNavigate = renderSidebar(`${platformPaths.digitalHuman}/42`);
    fireEvent.click(screen.getByRole("link", { name: "前往 Orion 助手" }));

    expect(onNavigate).not.toHaveBeenCalled();
  });
});
