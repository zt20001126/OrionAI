import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DigitalHumanAvatarHost } from "./DigitalHumanAvatarHost";

vi.mock("../hooks/useAudioMouthLevel", () => ({ useAudioMouthLevel: () => 0 }));
vi.mock("../hooks/useVrmPointerLookTarget", () => ({
  useVrmPointerLookTarget: () => ({ current: null }),
}));
vi.mock("./DigitalHumanAvatar3D", () => ({
  DigitalHumanAvatar3D: ({
    cameraFraming,
    enableClickInteraction,
  }: {
    cameraFraming?: string;
    enableClickInteraction?: boolean;
  }) => (
    <div
      data-camera-framing={cameraFraming}
      data-click-interaction={enableClickInteraction}
      data-testid="avatar"
    />
  ),
}));

describe("DigitalHumanAvatarHost", () => {
  it("enables click gestures in the digital human assistant host", () => {
    render(
      <DigitalHumanAvatarHost
        audioRef={createRef<HTMLAudioElement>()}
        isSpeaking={false}
        onLoadError={vi.fn()}
        status="idle"
      />,
    );

    expect(screen.getByTestId("avatar")).toHaveAttribute("data-click-interaction", "true");
    expect(screen.getByTestId("avatar")).toHaveAttribute("data-camera-framing", "home");
  });
});
