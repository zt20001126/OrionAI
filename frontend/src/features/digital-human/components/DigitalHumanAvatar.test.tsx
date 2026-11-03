import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DigitalHumanAvatar } from "./DigitalHumanAvatar";

afterEach(() => cleanup());

describe("DigitalHumanAvatar", () => {
  it.each([
    ["idle", "待机中"],
    ["listening", "正在聆听"],
    ["thinking", "正在思考"],
    ["speaking", "正在说话"],
  ] as const)("announces the %s state", (status, label) => {
    render(<DigitalHumanAvatar mouthOpen={0} status={status} />);

    expect(screen.getByRole("status")).toHaveTextContent(label);
    expect(screen.getByRole("img")).toHaveClass(`digital-human-avatar--${status}`);
  });

  it("maps the audio level to the mouth opening", () => {
    const { container } = render(<DigitalHumanAvatar mouthOpen={0.5} status="speaking" />);

    expect(container.querySelector(".digital-human-avatar__mouth")).toHaveAttribute("ry", "8");
  });
});
