import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HomeDigitalHuman } from "./HomeDigitalHuman";

vi.mock("../digital-human/hooks/useVrmPointerLookTarget", () => ({
  useVrmPointerLookTarget: () => ({ current: null }),
}));
vi.mock("../digital-human/components/DigitalHumanAvatar3D", () => ({
  DigitalHumanAvatar3D: ({ enableClickInteraction }: { enableClickInteraction?: boolean }) => (
    <div data-click-interaction={enableClickInteraction} data-testid="home-avatar" />
  ),
}));

describe("HomeDigitalHuman", () => {
  it("enables the shared avatar click gestures on the authentication page", async () => {
    render(<HomeDigitalHuman />);

    expect(await screen.findByTestId("home-avatar", {}, { timeout: 2000 })).toHaveAttribute(
      "data-click-interaction",
      "true",
    );
  });
});
