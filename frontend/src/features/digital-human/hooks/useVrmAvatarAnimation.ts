import { useEffect, useRef } from "react";
import { VRMExpressionPresetName, type VRM } from "@pixiv/three-vrm";
import { useFrame } from "@react-three/fiber";
import type { Object3D } from "three";

import type { DigitalHumanStatus } from "../types";

const BLINK_DURATION_SECONDS = 0.18;
const BLINK_MIN_INTERVAL_SECONDS = 2.8;
const BLINK_INTERVAL_VARIANCE_SECONDS = 2.6;
const UPPER_ARM_RELAX_ANGLE = 1.25;
const POSE_BLEND_SPEED = 4;
const CHEST_BREATHING_AMPLITUDE = 0.07;
const IDLE_HEAD_PITCH_AMPLITUDE = 0.06;
const IDLE_HEAD_TILT_AMPLITUDE = 0.06;
const LISTENING_HEAD_PITCH_AMPLITUDE = 0.22;
const LISTENING_HEAD_TILT = 0.11;
const THINKING_HEAD_PITCH = 0.3;
const THINKING_HEAD_TILT = -0.26;
const SPEAKING_HEAD_PITCH_AMPLITUDE = 0.16;
const SPEAKING_HEAD_TILT_AMPLITUDE = 0.09;
const SPEAKING_ARM_GESTURE_AMPLITUDE = 0.6;
const MOUTH_EXPRESSIONS = [VRMExpressionPresetName.Aa, VRMExpressionPresetName.Oh];

interface BlinkState {
  elapsed: number;
  waiting: number;
}

interface BreathingRig {
  chest: Object3D | null;
  chestBaseRotation: number;
  elapsed: number;
  head: Object3D | null;
  headBasePitch: number;
  headBaseTilt: number;
  leftUpperArm: Object3D | null;
  leftUpperArmBaseRotation: number;
  rightUpperArm: Object3D | null;
  rightUpperArmBaseRotation: number;
  smoothedArmRelaxAngle: number;
  smoothedHeadPitch: number;
  smoothedHeadTilt: number;
  smoothedSpeakingGesture: number;
}

interface StatusMotionTargets {
  headPitch: number;
  headTilt: number;
  speakingGesture: number;
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
    head: null,
    headBasePitch: 0,
    headBaseTilt: 0,
    leftUpperArm: null,
    leftUpperArmBaseRotation: 0,
    rightUpperArm: null,
    rightUpperArmBaseRotation: 0,
    smoothedArmRelaxAngle: 0,
    smoothedHeadPitch: 0,
    smoothedHeadTilt: 0,
    smoothedSpeakingGesture: 0,
  });
  const smoothedMouth = useRef(0);

  useEffect(() => {
    const chest = vrm.humanoid?.getNormalizedBoneNode("chest") ?? null;
    const head = vrm.humanoid?.getNormalizedBoneNode("head") ?? null;
    const leftUpperArm = vrm.humanoid?.getNormalizedBoneNode("leftUpperArm") ?? null;
    const rightUpperArm = vrm.humanoid?.getNormalizedBoneNode("rightUpperArm") ?? null;
    breathingRig.current = {
      chest,
      chestBaseRotation: chest?.rotation.x ?? 0,
      elapsed: 0,
      head,
      headBasePitch: head?.rotation.x ?? 0,
      headBaseTilt: head?.rotation.z ?? 0,
      leftUpperArm,
      leftUpperArmBaseRotation: leftUpperArm?.rotation.z ?? 0,
      rightUpperArm,
      rightUpperArmBaseRotation: rightUpperArm?.rotation.z ?? 0,
      smoothedArmRelaxAngle: 0,
      smoothedHeadPitch: 0,
      smoothedHeadTilt: 0,
      smoothedSpeakingGesture: 0,
    };

    return () => {
      if (chest) chest.rotation.x = breathingRig.current.chestBaseRotation;
      if (head) {
        head.rotation.x = breathingRig.current.headBasePitch;
        head.rotation.z = breathingRig.current.headBaseTilt;
      }
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
    rig.elapsed += delta;

    const targets = getStatusMotionTargets(status, rig.elapsed, !prefersReducedMotion.current);
    const blend = Math.min(1, delta * POSE_BLEND_SPEED);
    rig.smoothedArmRelaxAngle += (UPPER_ARM_RELAX_ANGLE - rig.smoothedArmRelaxAngle) * blend;
    rig.smoothedHeadPitch += (targets.headPitch - rig.smoothedHeadPitch) * blend;
    rig.smoothedHeadTilt += (targets.headTilt - rig.smoothedHeadTilt) * blend;
    rig.smoothedSpeakingGesture +=
      (targets.speakingGesture - rig.smoothedSpeakingGesture) * blend;

    if (rig.head) {
      rig.head.rotation.x = rig.headBasePitch + rig.smoothedHeadPitch;
      rig.head.rotation.z = rig.headBaseTilt + rig.smoothedHeadTilt;
    }

    if (rig.leftUpperArm) {
      rig.leftUpperArm.rotation.z = rig.leftUpperArmBaseRotation + rig.smoothedArmRelaxAngle;
    }
    if (rig.rightUpperArm) {
      rig.rightUpperArm.rotation.z =
        rig.rightUpperArmBaseRotation - rig.smoothedArmRelaxAngle + rig.smoothedSpeakingGesture;
    }

    if (rig.chest) {
      if (!prefersReducedMotion.current) {
        rig.chest.rotation.x =
          rig.chestBaseRotation + Math.sin(rig.elapsed * 1.4) * CHEST_BREATHING_AMPLITUDE;
      } else {
        rig.chest.rotation.x = rig.chestBaseRotation;
      }
    }

    vrm.update(delta);
  });
}

export function getStatusMotionTargets(
  status: DigitalHumanStatus,
  elapsed: number,
  motionEnabled: boolean,
): StatusMotionTargets {
  if (!motionEnabled) return { headPitch: 0, headTilt: 0, speakingGesture: 0 };

  switch (status) {
    case "listening":
      return {
        headPitch: Math.sin(elapsed * 1.25) * LISTENING_HEAD_PITCH_AMPLITUDE,
        headTilt: LISTENING_HEAD_TILT,
        speakingGesture: 0,
      };
    case "thinking":
      return {
        headPitch: THINKING_HEAD_PITCH,
        headTilt: THINKING_HEAD_TILT,
        speakingGesture: 0,
      };
    case "speaking":
      return {
        headPitch: Math.sin(elapsed * 1.8) * SPEAKING_HEAD_PITCH_AMPLITUDE,
        headTilt: Math.sin(elapsed * 0.9) * SPEAKING_HEAD_TILT_AMPLITUDE,
        speakingGesture: Math.sin(elapsed * 2.2) * SPEAKING_ARM_GESTURE_AMPLITUDE,
      };
    case "idle":
      return {
        headPitch: Math.sin(elapsed * 0.45) * IDLE_HEAD_PITCH_AMPLITUDE,
        headTilt: Math.sin(elapsed * 0.3) * IDLE_HEAD_TILT_AMPLITUDE,
        speakingGesture: 0,
      };
  }
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
