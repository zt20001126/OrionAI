import { describe, expect, it } from "vitest";

import {
  getVrmAvatarGestureDuration,
  getVrmAvatarGestureTargets,
  getIdleMotionTargets,
  getPointerLookTargets,
  getStatusMotionTargets,
} from "./useVrmAvatarAnimation";

describe("getPointerLookTargets", () => {
  it("limits pointer head movement and smoothly returns after the pointer stops", () => {
    const target = { x: 3, y: -3, updatedAt: 1000 };

    expect(getPointerLookTargets(target, 1200, true)).toEqual({ pitch: 0.34, yaw: 0.62 });
    const returning = getPointerLookTargets(target, 2800, true);

    expect(returning.pitch).toBeGreaterThan(0);
    expect(returning.pitch).toBeLessThan(0.34);
    expect(returning.yaw).toBeGreaterThan(0);
    expect(returning.yaw).toBeLessThan(0.62);
  });

  it("disables pointer movement when animation is disabled", () => {
    expect(getPointerLookTargets({ x: 1, y: 1, updatedAt: 0 }, 0, false)).toEqual({
      pitch: 0,
      yaw: 0,
    });
  });
});

describe("getStatusMotionTargets", () => {
  it("adds a visible nod while listening", () => {
    const motion = getStatusMotionTargets("listening", Math.PI / 2 / 1.25, true);

    expect(motion.headPitch).toBeCloseTo(0.22);
    expect(motion.headTilt).toBeCloseTo(0.11);
    expect(motion.headYaw).toBe(0);
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
    expect(motion.headYaw).toBeCloseTo(Math.sin((Math.PI / 0.9) * 0.24) * 0.045);
  });

  it("disables body motion when reduced motion is requested", () => {
    expect(getStatusMotionTargets("speaking", 2, false)).toEqual({
      headPitch: 0,
      headTilt: 0,
      headYaw: 0,
      speakingGesture: 0,
    });
  });

  it("keeps idle arm sway subtle and includes the occasional weight shift", () => {
    const motion = getIdleMotionTargets(1, 0.02, true);

    expect(Math.abs(motion.armSway)).toBeLessThanOrEqual(0.008);
    expect(Math.abs(motion.shoulderSway)).toBeLessThanOrEqual(0.01);
    expect(motion.weightShift).toBe(0.02);
  });

  it("disables idle motion targets when reduced motion is requested", () => {
    expect(getIdleMotionTargets(1, 0.02, false)).toEqual({
      armSway: 0,
      shoulderSway: 0,
      weightShift: 0,
    });
  });
});

describe("VRM avatar click gestures", () => {
  it("raises the waving arm and produces three full forearm swings", () => {
    const waveSamples = [0.5, 0.7, 0.9, 1.1, 1.3, 1.5].map(
      (elapsed) =>
        getVrmAvatarGestureTargets({ kind: "wave", elapsed, direction: 1 }).rightElbowWave,
    );

    expect(getVrmAvatarGestureDuration("wave")).toBe(2);
    expect(getVrmAvatarGestureTargets({ kind: "wave", elapsed: 0.4, direction: 1 })).toMatchObject({
      armBlend: 1,
      rightUpperArmRaise: expect.any(Number),
    });
    expect(
      getVrmAvatarGestureTargets({ kind: "wave", elapsed: 0.4, direction: 1 }).rightUpperArmRaise,
    ).toBeGreaterThan(2.3);
    expect(waveSamples[0]).toBeGreaterThan(0.55);
    expect(waveSamples[1]).toBeLessThan(-0.25);
    expect(waveSamples[2]).toBeGreaterThan(0.55);
    expect(waveSamples[3]).toBeLessThan(-0.25);
    expect(waveSamples[4]).toBeGreaterThan(0.55);
    expect(waveSamples[5]).toBeLessThan(-0.25);
    expect(getVrmAvatarGestureTargets({ kind: "wave", elapsed: 2, direction: 1 }).armBlend).toBe(0);
  });

  it("holds a 20 to 25 degree head tilt before smoothly releasing it", () => {
    const tilt = getVrmAvatarGestureTargets({ kind: "headTilt", elapsed: 0.8, direction: -1 });

    expect(getVrmAvatarGestureDuration("headTilt")).toBe(1.8);
    expect(tilt.headBlend).toBe(1);
    expect((Math.abs(tilt.headTilt) * 180) / Math.PI).toBeGreaterThanOrEqual(20);
    expect((Math.abs(tilt.headTilt) * 180) / Math.PI).toBeLessThanOrEqual(25);
    expect(
      getVrmAvatarGestureTargets({ kind: "headTilt", elapsed: 1.8, direction: -1 }).headBlend,
    ).toBe(0);
  });

  it("combines a happy expression with two nods and raised arms", () => {
    const happy = getVrmAvatarGestureTargets({ kind: "happy", elapsed: 0.4125, direction: 1 });

    expect(getVrmAvatarGestureDuration("happy")).toBe(2);
    expect(happy.expressionWeight).toBeGreaterThan(0.9);
    expect(happy.headPitch).toBeGreaterThan(0.18);
    expect(happy.leftUpperArmRaise).toBeLessThan(0);
    expect(happy.rightUpperArmRaise).toBeGreaterThan(0);
  });
});
