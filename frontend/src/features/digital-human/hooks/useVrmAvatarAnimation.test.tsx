import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Euler, Object3D, Quaternion, Vector3 } from "three";
import type { VRM } from "@pixiv/three-vrm";

import { useVrmAvatarAnimation } from "./useVrmAvatarAnimation";

const frameState = vi.hoisted(() => ({ frame: null as ((delta: number) => void) | null }));

vi.mock("@react-three/fiber", () => ({
  useFrame: (callback: (state: unknown, delta: number) => void) => {
    frameState.frame = (delta) => callback({}, delta);
  },
}));

afterEach(() => {
  frameState.frame = null;
  vi.unstubAllGlobals();
});

describe("useVrmAvatarAnimation gesture player", () => {
  it("allows only one click gesture to play at a time", () => {
    const { result } = renderHook(() => useVrmAvatarAnimation(createTestVrm().vrm, 0, "idle"));

    expect(result.current("wave")).toBe(true);
    expect(result.current("wave")).toBe(false);
    expect(result.current("headTilt")).toBe(false);
    expect(result.current("happy")).toBe(false);
  });

  it("raises the waving hand to head height through the right shoulder and arm chain", () => {
    const { head, rightHand, rightShoulder, scene, vrm } = createTestVrm();
    const { result } = renderHook(() => useVrmAvatarAnimation(vrm, 0, "idle"));

    expect(result.current("wave")).toBe(true);
    act(() => frameState.frame?.(0.45));
    scene.updateMatrixWorld(true);

    const headPosition = head.getWorldPosition(new Vector3());
    const shoulderPosition = rightShoulder.getWorldPosition(new Vector3());
    const handPosition = rightHand.getWorldPosition(new Vector3());
    expect(handPosition.y).toBeGreaterThan(shoulderPosition.y);
    expect(handPosition.y).toBeGreaterThan(headPosition.y - 0.05);
  });

  it("combines neck and head rotations for a visible 20 to 25 degree tilt", () => {
    const { head, neck, scene, vrm } = createTestVrm();
    const { result } = renderHook(() => useVrmAvatarAnimation(vrm, 0, "idle"));

    expect(result.current("headTilt")).toBe(true);
    act(() => frameState.frame?.(0.25));
    scene.updateMatrixWorld(true);

    const worldRotation = new Euler().setFromQuaternion(
      head.getWorldQuaternion(new Quaternion()),
      "XYZ",
    );
    expect((Math.abs(worldRotation.z) * 180) / Math.PI).toBeGreaterThanOrEqual(20);
    expect((Math.abs(worldRotation.z) * 180) / Math.PI).toBeLessThanOrEqual(25);
    expect(Math.abs(neck.rotation.z)).toBeGreaterThan(0);
  });

  it("applies the VRM happy expression during the two-nod response", () => {
    const { expressionValues, vrm } = createTestVrm();
    const { result } = renderHook(() => useVrmAvatarAnimation(vrm, 0, "idle"));

    expect(result.current("happy")).toBe(true);
    act(() => frameState.frame?.(0.4125));

    const happyWeight = expressionValues.find(([name]) => name === "happy")?.[1];
    expect(happyWeight).toBeGreaterThan(0.9);
  });
});

function createTestVrm() {
  const scene = new Object3D();
  const bones = new Map<string, Object3D>();
  const addBone = (name: string, parent: Object3D, position: readonly [number, number, number]) => {
    const bone = new Object3D();
    bone.position.set(...position);
    parent.add(bone);
    bones.set(name, bone);
    return bone;
  };

  const hips = addBone("hips", scene, [0, 0.84, 0]);
  const spine = addBone("spine", hips, [0, 0.26, 0]);
  const chest = addBone("chest", spine, [0, 0.086, 0]);
  const upperChest = addBone("upperChest", chest, [0, 0.109, 0]);
  const neck = addBone("neck", upperChest, [0, 0.134, 0]);
  const head = addBone("head", neck, [0, 0.076, 0]);
  const rightShoulder = addBone("rightShoulder", upperChest, [0.022, 0.107, 0.03]);
  const rightUpperArm = addBone("rightUpperArm", rightShoulder, [0.085, -0.013, 0]);
  const rightLowerArm = addBone("rightLowerArm", rightUpperArm, [0.222, 0, 0]);
  const rightHand = addBone("rightHand", rightLowerArm, [0.206, 0, 0]);
  const leftShoulder = addBone("leftShoulder", upperChest, [-0.022, 0.107, 0.03]);
  const leftUpperArm = addBone("leftUpperArm", leftShoulder, [-0.085, -0.013, 0]);
  const leftLowerArm = addBone("leftLowerArm", leftUpperArm, [-0.222, 0, 0]);
  addBone("leftHand", leftLowerArm, [-0.206, 0, 0]);

  const expressionValues: Array<[string, number]> = [];
  const vrm = {
    expressionManager: {
      getExpression: (name: string) => (name === "happy" ? {} : null),
      setValue: (name: string, weight: number) => expressionValues.push([name, weight]),
    },
    humanoid: { getNormalizedBoneNode: (name: string) => bones.get(name) ?? null },
    scene,
    update: vi.fn(),
  } as unknown as VRM;

  const mediaQuery = {
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  } as unknown as MediaQueryList;
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => mediaQuery),
  );

  return { expressionValues, head, neck, rightHand, rightShoulder, scene, vrm };
}
