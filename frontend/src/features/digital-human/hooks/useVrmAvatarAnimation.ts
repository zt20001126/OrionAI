import { useEffect, useRef } from "react";
import { VRMExpressionPresetName, type VRM } from "@pixiv/three-vrm";
import { useFrame } from "@react-three/fiber";
import type { Object3D } from "three";

import type { DigitalHumanStatus } from "../types";

const BLINK_DURATION_SECONDS = 0.18;
const BLINK_MIN_INTERVAL_SECONDS = 2.8;
const BLINK_INTERVAL_VARIANCE_SECONDS = 2.6;
const UPPER_ARM_RELAX_ANGLE = 0.82;
const MOUTH_EXPRESSIONS = [VRMExpressionPresetName.Aa, VRMExpressionPresetName.Oh];

interface BlinkState {
  elapsed: number;
  waiting: number;
}

interface BreathingRig {
  chest: Object3D | null;
  chestBaseRotation: number;
  elapsed: number;
  leftUpperArm: Object3D | null;
  leftUpperArmBaseRotation: number;
  rightUpperArm: Object3D | null;
  rightUpperArmBaseRotation: number;
}

/** 驱动 VRM 的眨眼、轻微呼吸和音量关联嘴型，不处理语音播放。 */
export function useVrmAvatarAnimation(
  vrm: VRM,
  mouthOpen: number,
  status: DigitalHumanStatus,
): void {
  const blinkState = useRef<BlinkState>({ elapsed: 0, waiting: BLINK_MIN_INTERVAL_SECONDS });
  const prefersReducedMotion = useRef(false);
  const breathingRig = useRef<BreathingRig>({
    chest: null,
    chestBaseRotation: 0,
    elapsed: 0,
    leftUpperArm: null,
    leftUpperArmBaseRotation: 0,
    rightUpperArm: null,
    rightUpperArmBaseRotation: 0,
  });
  const smoothedMouth = useRef(0);

  useEffect(() => {
    const chest = vrm.humanoid?.getNormalizedBoneNode("chest") ?? null;
    const leftUpperArm = vrm.humanoid?.getNormalizedBoneNode("leftUpperArm") ?? null;
    const rightUpperArm = vrm.humanoid?.getNormalizedBoneNode("rightUpperArm") ?? null;
    breathingRig.current = {
      chest,
      chestBaseRotation: chest?.rotation.x ?? 0,
      elapsed: 0,
      leftUpperArm,
      leftUpperArmBaseRotation: leftUpperArm?.rotation.z ?? 0,
      rightUpperArm,
      rightUpperArmBaseRotation: rightUpperArm?.rotation.z ?? 0,
    };

    return () => {
      if (chest) chest.rotation.x = breathingRig.current.chestBaseRotation;
      if (leftUpperArm) leftUpperArm.rotation.z = breathingRig.current.leftUpperArmBaseRotation;
      if (rightUpperArm) rightUpperArm.rotation.z = breathingRig.current.rightUpperArmBaseRotation;
    };
  }, [vrm]);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => {
      prefersReducedMotion.current = mediaQuery.matches;
    };
    updatePreference();
    mediaQuery.addEventListener("change", updatePreference);
    return () => mediaQuery.removeEventListener("change", updatePreference);
  }, []);

  useEffect(
    () => () => {
      const manager = vrm.expressionManager;
      if (manager?.getExpression(VRMExpressionPresetName.Blink)) {
        manager.setValue(VRMExpressionPresetName.Blink, 0);
      }
      for (const expression of MOUTH_EXPRESSIONS) {
        if (manager?.getExpression(expression)) manager.setValue(expression, 0);
      }
    },
    [vrm],
  );

  useFrame((_, delta) => {
    const manager = vrm.expressionManager;
    const blinkAmount = prefersReducedMotion.current
      ? 0
      : nextBlinkAmount(blinkState.current, delta);

    if (manager?.getExpression(VRMExpressionPresetName.Blink)) {
      manager.setValue(VRMExpressionPresetName.Blink, blinkAmount);
    }

    const mouthExpression = MOUTH_EXPRESSIONS.find((name) => manager?.getExpression(name));
    const targetMouth = status === "speaking" ? Math.min(1, Math.max(0, mouthOpen)) : 0;
    smoothedMouth.current += (targetMouth - smoothedMouth.current) * Math.min(1, delta * 14);
    if (mouthExpression) manager?.setValue(mouthExpression, smoothedMouth.current);

    const rig = breathingRig.current;
    if (rig.leftUpperArm) {
      rig.leftUpperArm.rotation.z = rig.leftUpperArmBaseRotation - UPPER_ARM_RELAX_ANGLE;
    }
    if (rig.rightUpperArm) {
      rig.rightUpperArm.rotation.z = rig.rightUpperArmBaseRotation + UPPER_ARM_RELAX_ANGLE;
    }

    if (rig.chest) {
      if (!prefersReducedMotion.current && (status === "idle" || status === "thinking")) {
        rig.elapsed += delta;
        rig.chest.rotation.x = rig.chestBaseRotation + Math.sin(rig.elapsed * 1.4) * 0.012;
      } else {
        rig.chest.rotation.x = rig.chestBaseRotation;
      }
    }

    vrm.update(delta);
  });
}

function nextBlinkAmount(blink: BlinkState, delta: number): number {
  if (blink.waiting > 0) {
    blink.waiting -= delta;
    return 0;
  }

  blink.elapsed += delta;
  if (blink.elapsed >= BLINK_DURATION_SECONDS) {
    blink.elapsed = 0;
    blink.waiting = BLINK_MIN_INTERVAL_SECONDS + Math.random() * BLINK_INTERVAL_VARIANCE_SECONDS;
    return 0;
  }

  return Math.sin((blink.elapsed / BLINK_DURATION_SECONDS) * Math.PI);
}
