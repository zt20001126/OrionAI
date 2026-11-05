import { useEffect } from "react";
import { Raycaster, Vector2, Vector3 } from "three";
import type { Camera, Mesh, Object3D, WebGLRenderer } from "three";
import type { VRM } from "@pixiv/three-vrm";

import type { VrmAvatarGesture, VrmAvatarGesturePlayer } from "./useVrmAvatarAnimation";

export const VRM_AVATAR_CLICK_DELAY_MS = 280;

export type VrmAvatarClickRegion = "body" | "head";

interface PendingClick {
  clickedAt: number;
  region: VrmAvatarClickRegion;
  timeout: number;
}

export interface VrmAvatarClickDispatcher {
  dispose: () => void;
  handleClick: (region: VrmAvatarClickRegion, clickedAt?: number) => void;
}

interface VrmAvatarClickInteractionOptions {
  camera: Camera;
  enabled: boolean;
  renderer: WebGLRenderer;
  playGesture: VrmAvatarGesturePlayer;
  vrm: VRM;
}

/** Attach click picking to the avatar canvas without creating another render loop. */
export function useVrmAvatarClickInteraction({
  camera,
  enabled,
  renderer,
  playGesture,
  vrm,
}: VrmAvatarClickInteractionOptions): void {
  useEffect(() => {
    if (!enabled) return;

    const canvas = renderer.domElement;
    const raycaster = new Raycaster();
    const pointer = new Vector2();
    const dispatcher = createVrmAvatarClickDispatcher(playGesture);
    const neck = vrm.humanoid?.getNormalizedBoneNode("neck") ?? null;
    const head = vrm.humanoid?.getNormalizedBoneNode("head") ?? null;

    const onClick = (event: MouseEvent) => {
      if (event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
        return;
      }

      const bounds = canvas.getBoundingClientRect();
      if (bounds.width <= 0 || bounds.height <= 0) return;

      pointer.set(
        ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
        -((event.clientY - bounds.top) / bounds.height) * 2 + 1,
      );
      raycaster.setFromCamera(pointer, camera);
      vrm.scene.updateMatrixWorld(true);

      const hit = raycaster.intersectObject(vrm.scene, true).find((intersection) => {
        const mesh = intersection.object as Mesh;
        return mesh.visible && mesh.isMesh;
      });
      if (!hit) return;

      const region = classifyVrmAvatarHit(hit.point, neck, head);
      if (region) dispatcher.handleClick(region, event.timeStamp);
    };

    canvas.addEventListener("click", onClick);
    return () => {
      canvas.removeEventListener("click", onClick);
      dispatcher.dispose();
    };
  }, [camera, enabled, playGesture, renderer, vrm]);
}

/** Determine the head area from the normalized neck/head positions in world space. */
export function classifyVrmAvatarHit(
  hitPoint: Vector3 | null,
  neck: Object3D | null,
  head: Object3D | null,
): VrmAvatarClickRegion | null {
  if (!hitPoint) return null;
  if (!neck || !head) return "body";

  const neckY = neck.getWorldPosition(new Vector3()).y;
  const headY = head.getWorldPosition(new Vector3()).y;
  const headBoundary = neckY + (headY - neckY) * 0.45;

  return hitPoint.y >= headBoundary ? "head" : "body";
}

/** Delay a single-click gesture long enough to recognize a double-click. */
export function createVrmAvatarClickDispatcher(
  playGesture: VrmAvatarGesturePlayer,
  delayMs = VRM_AVATAR_CLICK_DELAY_MS,
): VrmAvatarClickDispatcher {
  let pending: PendingClick | null = null;

  const playSingleClick = (region: VrmAvatarClickRegion) => {
    const gesture: VrmAvatarGesture = region === "head" ? "headTilt" : "wave";
    playGesture(gesture);
  };

  return {
    handleClick(region, clickedAt = performance.now()) {
      if (pending && clickedAt >= pending.clickedAt && clickedAt - pending.clickedAt <= delayMs) {
        window.clearTimeout(pending.timeout);
        pending = null;
        playGesture("happy");
        return;
      }

      if (pending) {
        window.clearTimeout(pending.timeout);
        playSingleClick(pending.region);
        pending = null;
      }

      const nextPending: PendingClick = { clickedAt, region, timeout: 0 };
      nextPending.timeout = window.setTimeout(() => {
        if (pending !== nextPending) return;
        pending = null;
        playSingleClick(region);
      }, delayMs);
      pending = nextPending;
    },
    dispose() {
      if (pending) window.clearTimeout(pending.timeout);
      pending = null;
    },
  };
}
