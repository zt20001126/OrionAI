import { describe, expect, it } from "vitest";

import { getStatusMotionTargets } from "./useVrmAvatarAnimation";

describe("getStatusMotionTargets", () => {
  it("adds a small nod while listening", () => {
    const motion = getStatusMotionTargets("listening", Math.PI / 2 / 1.25, true);

    expect(motion.headPitch).toBeCloseTo(0.035);
    expect(motion.speakingGesture).toBe(0);
  });

  it("tilts the head while thinking", () => {
    const motion = getStatusMotionTargets("thinking", 1, true);

    expect(motion.headPitch).toBe(0.07);
    expect(motion.headTilt).toBe(-0.06);
  });

  it("uses a subtle arm gesture while speaking", () => {
    const motion = getStatusMotionTargets("speaking", Math.PI / 4.4, true);

    expect(motion.speakingGesture).toBeCloseTo(0.1);
  });

  it("disables body motion when reduced motion is requested", () => {
    expect(getStatusMotionTargets("speaking", 2, false)).toEqual({
      headPitch: 0,
      headTilt: 0,
      speakingGesture: 0,
    });
  });
});
