import { describe, expect, it } from "vitest";

import { getStatusMotionTargets } from "./useVrmAvatarAnimation";

describe("getStatusMotionTargets", () => {
  it("adds a visible nod while listening", () => {
    const motion = getStatusMotionTargets("listening", Math.PI / 2 / 1.25, true);

    expect(motion.headPitch).toBeCloseTo(0.22);
    expect(motion.headTilt).toBeCloseTo(0.11);
    expect(motion.speakingGesture).toBe(0);
  });

  it("tilts the head while thinking", () => {
    const motion = getStatusMotionTargets("thinking", 1, true);

    expect(motion.headPitch).toBe(0.3);
    expect(motion.headTilt).toBe(-0.26);
  });

  it("uses a broader arm gesture while speaking", () => {
    const motion = getStatusMotionTargets("speaking", Math.PI / 4.4, true);

    expect(motion.speakingGesture).toBeCloseTo(0.6);
  });

  it("adds visible idle head motion", () => {
    const motion = getStatusMotionTargets("idle", Math.PI / 0.9, true);

    expect(motion.headPitch).toBeCloseTo(0.06);
    expect(motion.headTilt).toBeCloseTo(Math.sin((Math.PI / 0.9) * 0.3) * 0.06);
  });

  it("disables body motion when reduced motion is requested", () => {
    expect(getStatusMotionTargets("speaking", 2, false)).toEqual({
      headPitch: 0,
      headTilt: 0,
      speakingGesture: 0,
    });
  });
});
