import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, renderHook } from "@testing-library/react";
import {
  BoxGeometry,
  Mesh,
  MeshBasicMaterial,
  Object3D,
  PerspectiveCamera,
  Scene,
  Vector3,
} from "three";
import type { WebGLRenderer } from "three";
import type { VRM } from "@pixiv/three-vrm";

import {
  classifyVrmAvatarHit,
  createVrmAvatarClickDispatcher,
  useVrmAvatarClickInteraction,
} from "./useVrmAvatarClickInteraction";
import type { VrmAvatarGesturePlayer } from "./useVrmAvatarAnimation";

afterEach(() => vi.useRealTimers());

describe("classifyVrmAvatarHit", () => {
  it("distinguishes the head region from the rest of the body using the humanoid bones", () => {
    const neck = new Object3D();
    const head = new Object3D();
    neck.position.y = 1.4;
    head.position.y = 1.5;

    expect(classifyVrmAvatarHit(new Vector3(0, 1.48, 0), neck, head)).toBe("head");
    expect(classifyVrmAvatarHit(new Vector3(0, 1.43, 0), neck, head)).toBe("body");
  });

  it("uses body gestures when the model lacks head or neck bones", () => {
    expect(classifyVrmAvatarHit(new Vector3(0, 2, 0), null, null)).toBe("body");
  });

  it("ignores clicks that did not hit the model", () => {
    expect(classifyVrmAvatarHit(null, new Object3D(), new Object3D())).toBeNull();
  });
});

describe("createVrmAvatarClickDispatcher", () => {
  it("waits briefly before dispatching a single body or head click", () => {
    vi.useFakeTimers();
    const playGesture = vi.fn();
    const dispatcher = createVrmAvatarClickDispatcher(playGesture);

    dispatcher.handleClick("body", 100);
    expect(playGesture).not.toHaveBeenCalled();

    vi.advanceTimersByTime(280);
    expect(playGesture).toHaveBeenCalledExactlyOnceWith("wave");
    dispatcher.dispose();
  });

  it("turns two valid model clicks into only one happy response", () => {
    vi.useFakeTimers();
    const playGesture = vi.fn();
    const dispatcher = createVrmAvatarClickDispatcher(playGesture);

    dispatcher.handleClick("head", 100);
    dispatcher.handleClick("body", 300);
    vi.advanceTimersByTime(400);

    expect(playGesture).toHaveBeenCalledExactlyOnceWith("happy");
    dispatcher.dispose();
  });

  it("cancels a pending click when its canvas interaction unmounts", () => {
    vi.useFakeTimers();
    const playGesture = vi.fn();
    const dispatcher = createVrmAvatarClickDispatcher(playGesture);

    dispatcher.handleClick("body", 100);
    dispatcher.dispose();
    vi.advanceTimersByTime(300);

    expect(playGesture).not.toHaveBeenCalled();
  });
});

describe("useVrmAvatarClickInteraction raycasting", () => {
  it.each([
    ["head", 30, "headTilt"],
    ["body", 60, "wave"],
  ] as const)("routes a raycast hit on the %s to %s", (_, clientY, gesture) => {
    vi.useFakeTimers();
    const playGesture = vi.fn(() => true);
    const { canvas, unmount } = mountAvatarClickInteraction(playGesture);

    fireEvent.click(canvas, { button: 0, clientX: 50, clientY });
    vi.advanceTimersByTime(280);

    expect(playGesture).toHaveBeenCalledExactlyOnceWith(gesture);
    unmount();
  });

  it("does not dispatch when the ray misses the avatar mesh", () => {
    vi.useFakeTimers();
    const playGesture = vi.fn(() => true);
    const { canvas, unmount } = mountAvatarClickInteraction(playGesture);

    fireEvent.click(canvas, { button: 0, clientX: 0, clientY: 50 });
    vi.advanceTimersByTime(300);

    expect(playGesture).not.toHaveBeenCalled();
    unmount();
  });
});

function mountAvatarClickInteraction(playGesture: VrmAvatarGesturePlayer) {
  const scene = new Scene();
  scene.add(new Mesh(new BoxGeometry(2, 2, 0.2), new MeshBasicMaterial()));

  const neck = new Object3D();
  neck.position.y = 0.8;
  const head = new Object3D();
  head.position.y = 1;
  scene.add(neck, head);

  const camera = new PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.z = 5;
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);

  const canvas = document.createElement("canvas");
  vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 100, 100));
  const renderer = { domElement: canvas } as unknown as WebGLRenderer;
  const vrm = {
    humanoid: {
      getNormalizedBoneNode: (boneName: string) =>
        boneName === "neck" ? neck : boneName === "head" ? head : null,
    },
    scene,
  } as unknown as VRM;
  const { unmount } = renderHook(() =>
    useVrmAvatarClickInteraction({
      camera,
      enabled: true,
      renderer,
      playGesture,
      vrm,
    }),
  );

  return { canvas, unmount };
}
