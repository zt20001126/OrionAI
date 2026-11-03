import { useLayoutEffect } from "react";
import type { RefObject } from "react";
import type { VRM } from "@pixiv/three-vrm";
import { useThree } from "@react-three/fiber";
import { Box3, Vector3 } from "three";
import type { PerspectiveCamera } from "three";

import { useVrmAvatarAnimation } from "../hooks/useVrmAvatarAnimation";
import type { DigitalHumanStatus } from "../types";

interface VrmAvatarSceneProps {
  cameraRef: RefObject<PerspectiveCamera | null>;
  mouthOpen: number;
  status: DigitalHumanStatus;
  vrm: VRM;
}

/** 将模型包围盒居中取景，让不同高度的 VRM 使用一致的上半身构图。 */
export function VrmAvatarScene({ cameraRef, mouthOpen, status, vrm }: VrmAvatarSceneProps) {
  const size = useThree((state) => state.size);
  useVrmAvatarAnimation(vrm, mouthOpen, status);

  useLayoutEffect(() => {
    const camera = cameraRef.current;
    if (!camera) return;

    vrm.scene.updateMatrixWorld(true);
    const bounds = new Box3().setFromObject(vrm.scene);
    const dimensions = bounds.getSize(new Vector3());
    const center = bounds.getCenter(new Vector3());
    if (dimensions.y <= 0) return;

    // Frame the head and upper torso. Do not fit the whole model width: T-pose arms
    // otherwise force the camera far back and make the avatar appear full-body.
    const framingHeight = dimensions.y * 0.56;
    const verticalFieldOfView = (camera.fov * Math.PI) / 180;
    const halfFovTangent = Math.tan(verticalFieldOfView / 2);
    const distanceByHeight = framingHeight / (2 * halfFovTangent);
    const distance = distanceByHeight * 1.08;
    const target = new Vector3(center.x, bounds.min.y + dimensions.y * 0.72, center.z);

    camera.position.set(target.x, target.y, target.z + distance);
    camera.up.set(0, 1, 0);
    camera.near = Math.max(dimensions.y * 0.005, 0.01);
    camera.far = Math.max(dimensions.y * 20, distance + dimensions.y * 4);
    camera.lookAt(target);
    camera.updateProjectionMatrix();
  }, [cameraRef, size.width, size.height, vrm]);

  return <primitive object={vrm.scene} />;
}
