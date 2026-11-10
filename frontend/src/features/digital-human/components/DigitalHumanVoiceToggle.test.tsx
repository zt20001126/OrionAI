import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DigitalHumanVoiceToggle } from "./DigitalHumanVoiceToggle";

describe("DigitalHumanVoiceToggle", () => {
  it("用可访问的开关语义即时切换语音状态", () => {
    const onChange = vi.fn();
    const { rerender } = render(<DigitalHumanVoiceToggle enabled onChange={onChange} />);

    const toggle = screen.getByRole("switch", { name: "关闭语音播报" });
    expect(toggle).toHaveAttribute("aria-checked", "true");
    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(false);

    rerender(<DigitalHumanVoiceToggle enabled={false} onChange={onChange} />);
    expect(screen.getByRole("switch", { name: "开启语音播报" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });
});
