import { useLayoutEffect } from "react";
import type { RefObject } from "react";
import type { VRM } from "@pixiv/three-vrm";
import { useThree } from "@react-three/fiber";
import { Box3, Vector3 } from "three";
import type { PerspectiveCamera } from "three";

import { useVrmAvatarAnimation, type VrmLookTarget } from "../hooks/useVrmAvatarAnimation";
import type { DigitalHumanStatus } from "../types";

interface VrmAvatarSceneProps {
  cameraRef: RefObject<PerspectiveCamera | null>;
  lookTargetRef?: RefObject<VrmLookTarget | null>;
  mouthOpen: number;
  presentation?: "assistant" | "home";
  status: DigitalHumanStatus;
  vrm: VRM;
}

/** 按模型包围盒和展示场景自动取景。 */
export function VrmAvatarScene({
  cameraRef,
  lookTargetRef,
  mouthOpen,
  presentation = "assistant",
  status,
  vrm,
}: VrmAvatarSceneProps) {
  const size = useThree((state) => state.size);
  useVrmAvatarAnimation(vrm, mouthOpen, status, lookTargetRef);

  useLayoutEffect(() => {
    const camera = cameraRef.current;
    if (!camera) return;

    vrm.scene.updateMatrixWorld(true);
    const bounds = new Box3().setFromObject(vrm.scene);
    const dimensions = bounds.getSize(new Vector3());
    const center = bounds.getCenter(new Vector3());
    if (dimensions.y <= 0) return;

    // 助手页面聚焦头部和上身；首页展示更多身体，同时避免让水平手臂影响取景。
    const framingHeight = dimensions.y * (presentation === "home" ? 0.94 : 0.56);
    const verticalFieldOfView = (camera.fov * Math.PI) / 180;
    const halfFovTangent = Math.tan(verticalFieldOfView / 2);
    const distanceByHeight = framingHeight / (2 * halfFovTangent);
    const distance = distanceByHeight * 1.08;
    const targetHeightRatio = presentation === "home" ? 0.54 : 0.72;
    const target = new Vector3(center.x, bounds.min.y + dimensions.y * targetHeightRatio, center.z);

    camera.position.set(target.x, target.y, target.z + distance);
    camera.up.set(0, 1, 0);
    camera.near = Math.max(dimensions.y * 0.005, 0.01);
    camera.far = Math.max(dimensions.y * 20, distance + dimensions.y * 4);
    camera.lookAt(target);
    camera.updateProjectionMatrix();
  }, [cameraRef, presentation, size.width, size.height, vrm]);

  return <primitive object={vrm.scene} />;
}
