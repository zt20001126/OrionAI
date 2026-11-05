import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PlatformSidebar } from "./PlatformSidebar";
import { navigationItems, platformPaths, type PlatformRoute } from "./platformData";

vi.mock("../auth/ProductIntro", () => ({ BrandMark: () => null }));
vi.mock("../membership/MembershipEntry", () => ({ MembershipEntry: () => null }));
vi.mock("../notifications/NotificationBell", () => ({ NotificationBell: () => null }));
vi.mock("./ProfileMenu", () => ({ ProfileMenu: () => null }));

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
  it("places My Digital Human between My Skills and Conversations", () => {
    expect(navigationItems.map(({ path }) => path)).toEqual([
      platformPaths.market,
      platformPaths.mySkills,
      platformPaths.digitalHuman,
      platformPaths.sessions,
      platformPaths.knowledge,
      platformPaths.tools,
    ]);
  });

  it("selects the digital human item for a conversation route and navigates to its root", () => {
    const onNavigate = renderSidebar(`${platformPaths.digitalHuman}/42`);
    const navigation = screen.getByRole("navigation");
    const item = within(navigation).getByRole("link", { name: "我的数字人" });

    expect(item).toHaveAttribute("aria-current", "page");
    fireEvent.click(item);
    expect(onNavigate).toHaveBeenCalledWith(platformPaths.digitalHuman);
  });
});
