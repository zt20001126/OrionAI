import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { VRMExpressionPresetName, type VRM, type VRMHumanBoneName } from "@pixiv/three-vrm";
import { useFrame } from "@react-three/fiber";
import { Euler, Quaternion } from "three";
import type { Object3D } from "three";

import type { DigitalHumanStatus } from "../types";
import type { VrmLookTarget } from "./useVrmPointerLookTarget";

const BLINK_DURATION_SECONDS = 0.18;
const BLINK_MIN_INTERVAL_SECONDS = 2.8;
const BLINK_INTERVAL_VARIANCE_SECONDS = 2.6;
const BLINK_BLEND_SPEED = 32;
const ARM_RELAX_ANGLE = 1.25;
const SHOULDER_RELAX_SHARE = 0.12;
const ELBOW_FLEX_ANGLE = 0.12;
const WRIST_FLEX_ANGLE = 0.045;
const POSE_BLEND_SPEED = 4;
const CHEST_BREATHING_AMPLITUDE = 0.022;
const CHEST_BREATHING_FREQUENCY = 0.9;
const IDLE_HEAD_PITCH_AMPLITUDE = 0.06;
const IDLE_HEAD_YAW_AMPLITUDE = 0.045;
const IDLE_HEAD_TILT_AMPLITUDE = 0.06;
const IDLE_HEAD_PITCH_FREQUENCY = 0.45;
const IDLE_HEAD_YAW_FREQUENCY = 0.24;
const IDLE_HEAD_TILT_FREQUENCY = 0.3;
const NECK_MOTION_SHARE = 0.24;
const POINTER_HEAD_PITCH_AMPLITUDE = 0.34;
const POINTER_HEAD_YAW_AMPLITUDE = 0.62;
const IDLE_SHOULDER_SWAY_AMPLITUDE = 0.01;
const IDLE_SHOULDER_SWAY_FREQUENCY = 0.42;
const IDLE_ARM_SWAY_AMPLITUDE = 0.008;
const IDLE_ARM_SWAY_FREQUENCY = 0.32;
const IDLE_ARM_SWAY_PHASE = 0.7;
const WEIGHT_SHIFT_MAX_ANGLE = 0.022;
const WEIGHT_SHIFT_START_MIN_SECONDS = 5;
const WEIGHT_SHIFT_START_MAX_SECONDS = 9;
const WEIGHT_SHIFT_DURATION_MIN_SECONDS = 3.2;
const WEIGHT_SHIFT_DURATION_MAX_SECONDS = 4.4;
const WEIGHT_SHIFT_REST_MIN_SECONDS = 6;
const WEIGHT_SHIFT_REST_MAX_SECONDS = 10;
const WEIGHT_SHIFT_RESUME_DELAY_SECONDS = 2.5;
const SPINE_COUNTER_SHIFT_SHARE = 0.42;
const LISTENING_HEAD_PITCH_AMPLITUDE = 0.22;
const LISTENING_HEAD_TILT = 0.11;
const LISTENING_HEAD_PITCH_FREQUENCY = 1.25;
const THINKING_HEAD_PITCH = 0.3;
const THINKING_HEAD_TILT = -0.26;
const SPEAKING_HEAD_PITCH_AMPLITUDE = 0.16;
const SPEAKING_HEAD_PITCH_FREQUENCY = 1.8;
const SPEAKING_HEAD_TILT_AMPLITUDE = 0.09;
const SPEAKING_HEAD_TILT_FREQUENCY = 0.9;
const SPEAKING_ARM_GESTURE_AMPLITUDE = 0.6;
const SPEAKING_ARM_GESTURE_FREQUENCY = 2.2;
const MOUTH_EXPRESSIONS = [VRMExpressionPresetName.Aa, VRMExpressionPresetName.Oh];
const FINGER_SEGMENT_CURL_FACTORS = [1, 0.72, 0.52] as const;
const THUMB_SEGMENT_CURL_FACTORS = [0.65, 1, 0.68] as const;

interface BlinkState {
  elapsed: number;
  waiting: number;
}

interface PoseBone {
  node: Object3D;
  baseRotation: Quaternion;
}

interface FingerPose {
  bone: PoseBone;
  bendAngle: number;
  side: 1 | -1;
}

interface FingerPoseConfig {
  leftBones: readonly VRMHumanBoneName[];
  rightBones: readonly VRMHumanBoneName[];
  bendAngle: number;
  segmentCurlFactors: readonly number[];
}

interface WeightShiftState {
  direction: 1 | -1;
  duration: number;
  elapsed: number;
  waiting: number;
}

interface BreathingRig {
  chest: PoseBone | null;
  fingers: FingerPose[];
  head: PoseBone | null;
  hips: PoseBone | null;
  leftHand: PoseBone | null;
  leftLowerArm: PoseBone | null;
  leftShoulder: PoseBone | null;
  leftUpperArm: PoseBone | null;
  neck: PoseBone | null;
  rightHand: PoseBone | null;
  rightLowerArm: PoseBone | null;
  rightShoulder: PoseBone | null;
  rightUpperArm: PoseBone | null;
  spine: PoseBone | null;
  elapsed: number;
  smoothedArmRelaxAngle: number;
  smoothedArmSway: number;
  smoothedBreathing: number;
  smoothedElbowFlex: number;
  smoothedFingerCurl: number;
  smoothedHeadPitch: number;
  smoothedHeadTilt: number;
  smoothedHeadYaw: number;
  smoothedShoulderSway: number;
  smoothedSpeakingGesture: number;
  smoothedWeightShift: number;
  smoothedWristFlex: number;
  weightShift: WeightShiftState;
  scratchEuler: Euler;
  scratchQuaternion: Quaternion;
}

interface StatusMotionTargets {
  headPitch: number;
  headTilt: number;
  headYaw: number;
  speakingGesture: number;
}

interface IdleMotionTargets {
  armSway: number;
  shoulderSway: number;
  weightShift: number;
}

const FINGER_POSE_CONFIGS: readonly FingerPoseConfig[] = [
  {
    leftBones: ["leftThumbMetacarpal", "leftThumbProximal", "leftThumbDistal"],
    rightBones: ["rightThumbMetacarpal", "rightThumbProximal", "rightThumbDistal"],
    bendAngle: 0.12,
    segmentCurlFactors: THUMB_SEGMENT_CURL_FACTORS,
  },
  {
    leftBones: ["leftIndexProximal", "leftIndexIntermediate", "leftIndexDistal"],
    rightBones: ["rightIndexProximal", "rightIndexIntermediate", "rightIndexDistal"],
    bendAngle: 0.18,
    segmentCurlFactors: FINGER_SEGMENT_CURL_FACTORS,
  },
  {
    leftBones: ["leftMiddleProximal", "leftMiddleIntermediate", "leftMiddleDistal"],
    rightBones: ["rightMiddleProximal", "rightMiddleIntermediate", "rightMiddleDistal"],
    bendAngle: 0.16,
    segmentCurlFactors: FINGER_SEGMENT_CURL_FACTORS,
  },
  {
    leftBones: ["leftRingProximal", "leftRingIntermediate", "leftRingDistal"],
    rightBones: ["rightRingProximal", "rightRingIntermediate", "rightRingDistal"],
    bendAngle: 0.15,
    segmentCurlFactors: FINGER_SEGMENT_CURL_FACTORS,
  },
  {
    leftBones: ["leftLittleProximal", "leftLittleIntermediate", "leftLittleDistal"],
    rightBones: ["rightLittleProximal", "rightLittleIntermediate", "rightLittleDistal"],
    bendAngle: 0.13,
    segmentCurlFactors: FINGER_SEGMENT_CURL_FACTORS,
  },
];

/** 单点驱动 VRM 骨骼；后续 VRMA 状态驱动应接管对应骨骼，避免多路写入冲突。 */
export function useVrmAvatarAnimation(
  vrm: VRM,
  mouthOpen: number,
  status: DigitalHumanStatus,
  lookTargetRef?: RefObject<VrmLookTarget | null>,
): void {
  const blinkState = useRef<BlinkState>({ elapsed: 0, waiting: randomBlinkInterval() });
  const smoothedBlink = useRef(0);
  const prefersReducedMotion = useRef(false);
  const breathingRig = useRef<BreathingRig | null>(null);
  const smoothedMouth = useRef(0);

  useEffect(() => {
    const rig = createBreathingRig(vrm);
    breathingRig.current = rig;

    return () => {
      restoreBreathingRig(rig);
      if (breathingRig.current === rig) breathingRig.current = null;
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
    const motionEnabled = !prefersReducedMotion.current;
    const blinkAmount = nextBlinkAmount(blinkState.current, delta);
    const blinkTarget = motionEnabled ? blinkAmount : 0;
    const blinkBlend = 1 - Math.exp(-BLINK_BLEND_SPEED * delta);
    smoothedBlink.current += (blinkTarget - smoothedBlink.current) * blinkBlend;

    if (manager?.getExpression(VRMExpressionPresetName.Blink)) {
      manager.setValue(VRMExpressionPresetName.Blink, smoothedBlink.current);
    }

    const mouthExpression = MOUTH_EXPRESSIONS.find((name) => manager?.getExpression(name));
    const targetMouth = status === "speaking" ? Math.min(1, Math.max(0, mouthOpen)) : 0;
    smoothedMouth.current += (targetMouth - smoothedMouth.current) * Math.min(1, delta * 14);
    if (mouthExpression) manager?.setValue(mouthExpression, smoothedMouth.current);

    const rig = breathingRig.current;
    if (!rig) {
      vrm.update(delta);
      return;
    }

    rig.elapsed += delta;
    const weightShiftTarget = nextWeightShiftAmount(
      rig.weightShift,
      delta,
      motionEnabled && status === "idle",
    );
    const idleTargets = getIdleMotionTargets(
      rig.elapsed,
      weightShiftTarget,
      motionEnabled && status === "idle",
    );
    const statusTargets = getStatusMotionTargets(status, rig.elapsed, motionEnabled);
    const pointerLook = getPointerLookTargets(
      lookTargetRef?.current ?? null,
      performance.now(),
      motionEnabled && status === "idle",
    );
    statusTargets.headPitch += pointerLook.pitch;
    statusTargets.headYaw += pointerLook.yaw;
    const breathingTarget = motionEnabled
      ? Math.sin(rig.elapsed * CHEST_BREATHING_FREQUENCY) * CHEST_BREATHING_AMPLITUDE
      : 0;
    const blend = 1 - Math.exp(-POSE_BLEND_SPEED * delta);

    rig.smoothedArmRelaxAngle += (ARM_RELAX_ANGLE - rig.smoothedArmRelaxAngle) * blend;
    rig.smoothedArmSway += (idleTargets.armSway - rig.smoothedArmSway) * blend;
    rig.smoothedBreathing += (breathingTarget - rig.smoothedBreathing) * blend;
    rig.smoothedElbowFlex += (ELBOW_FLEX_ANGLE - rig.smoothedElbowFlex) * blend;
    rig.smoothedFingerCurl += (1 - rig.smoothedFingerCurl) * blend;
    rig.smoothedHeadPitch += (statusTargets.headPitch - rig.smoothedHeadPitch) * blend;
    rig.smoothedHeadTilt += (statusTargets.headTilt - rig.smoothedHeadTilt) * blend;
    rig.smoothedHeadYaw += (statusTargets.headYaw - rig.smoothedHeadYaw) * blend;
    rig.smoothedShoulderSway += (idleTargets.shoulderSway - rig.smoothedShoulderSway) * blend;
    rig.smoothedSpeakingGesture +=
      (statusTargets.speakingGesture - rig.smoothedSpeakingGesture) * blend;
    rig.smoothedWeightShift += (idleTargets.weightShift - rig.smoothedWeightShift) * blend;
    rig.smoothedWristFlex += (WRIST_FLEX_ANGLE - rig.smoothedWristFlex) * blend;

    const shoulderRelax = rig.smoothedArmRelaxAngle * SHOULDER_RELAX_SHARE;
    const upperArmRelax = rig.smoothedArmRelaxAngle * (1 - SHOULDER_RELAX_SHARE);
    const leftShoulderSway = rig.smoothedShoulderSway;
    applyBoneRotation(rig.hips, 0, 0, rig.smoothedWeightShift, rig);
    applyBoneRotation(rig.spine, 0, 0, -rig.smoothedWeightShift * SPINE_COUNTER_SHIFT_SHARE, rig);
    applyBoneRotation(rig.chest, rig.smoothedBreathing, 0, 0, rig);
    applyBoneRotation(
      rig.neck,
      rig.smoothedHeadPitch * NECK_MOTION_SHARE,
      rig.smoothedHeadYaw * NECK_MOTION_SHARE,
      rig.smoothedHeadTilt * NECK_MOTION_SHARE,
      rig,
    );
    applyBoneRotation(
      rig.head,
      rig.smoothedHeadPitch * (1 - NECK_MOTION_SHARE),
      rig.smoothedHeadYaw * (1 - NECK_MOTION_SHARE),
      rig.smoothedHeadTilt * (1 - NECK_MOTION_SHARE),
      rig,
    );
    applyBoneRotation(rig.leftShoulder, 0, 0, shoulderRelax + leftShoulderSway, rig);
    applyBoneRotation(rig.rightShoulder, 0, 0, -(shoulderRelax + leftShoulderSway), rig);
    applyBoneRotation(rig.leftUpperArm, 0, 0, upperArmRelax + rig.smoothedArmSway, rig);
    applyBoneRotation(
      rig.rightUpperArm,
      0,
      0,
      -(upperArmRelax + rig.smoothedArmSway) + rig.smoothedSpeakingGesture,
      rig,
    );
    applyBoneRotation(rig.leftLowerArm, 0, rig.smoothedElbowFlex, 0, rig);
    applyBoneRotation(rig.rightLowerArm, 0, -rig.smoothedElbowFlex, 0, rig);
    applyBoneRotation(rig.leftHand, 0, rig.smoothedWristFlex, 0, rig);
    applyBoneRotation(rig.rightHand, 0, -rig.smoothedWristFlex, 0, rig);

    for (const finger of rig.fingers) {
      applyBoneRotation(
        finger.bone,
        0,
        finger.side * finger.bendAngle * rig.smoothedFingerCurl,
        0,
        rig,
      );
    }

    vrm.update(delta);
  });
}

export function getPointerLookTargets(
  target: VrmLookTarget | null,
  nowMs: number,
  motionEnabled: boolean,
): { pitch: number; yaw: number } {
  if (!target || !motionEnabled) return { pitch: 0, yaw: 0 };

  const idleDurationMs = Math.max(0, nowMs - target.updatedAt - 800);
  const returnBlend = Math.exp(-idleDurationMs / 900);
  const x = Math.max(-1, Math.min(1, target.x));
  const y = Math.max(-1, Math.min(1, target.y));

  return {
    pitch: -y * POINTER_HEAD_PITCH_AMPLITUDE * returnBlend,
    yaw: x * POINTER_HEAD_YAW_AMPLITUDE * returnBlend,
  };
}

export function getStatusMotionTargets(
  status: DigitalHumanStatus,
  elapsed: number,
  motionEnabled: boolean,
): StatusMotionTargets {
  if (!motionEnabled) {
    return { headPitch: 0, headTilt: 0, headYaw: 0, speakingGesture: 0 };
  }

  switch (status) {
    case "listening":
      return {
        headPitch:
          Math.sin(elapsed * LISTENING_HEAD_PITCH_FREQUENCY) * LISTENING_HEAD_PITCH_AMPLITUDE,
        headTilt: LISTENING_HEAD_TILT,
        headYaw: 0,
        speakingGesture: 0,
      };
    case "thinking":
      return {
        headPitch: THINKING_HEAD_PITCH,
        headTilt: THINKING_HEAD_TILT,
        headYaw: 0,
        speakingGesture: 0,
      };
    case "speaking":
      return {
        headPitch:
          Math.sin(elapsed * SPEAKING_HEAD_PITCH_FREQUENCY) * SPEAKING_HEAD_PITCH_AMPLITUDE,
        headTilt: Math.sin(elapsed * SPEAKING_HEAD_TILT_FREQUENCY) * SPEAKING_HEAD_TILT_AMPLITUDE,
        headYaw: 0,
        speakingGesture:
          Math.sin(elapsed * SPEAKING_ARM_GESTURE_FREQUENCY) * SPEAKING_ARM_GESTURE_AMPLITUDE,
      };
    case "idle":
      return {
        headPitch: Math.sin(elapsed * IDLE_HEAD_PITCH_FREQUENCY) * IDLE_HEAD_PITCH_AMPLITUDE,
        headTilt: Math.sin(elapsed * IDLE_HEAD_TILT_FREQUENCY) * IDLE_HEAD_TILT_AMPLITUDE,
        headYaw: Math.sin(elapsed * IDLE_HEAD_YAW_FREQUENCY) * IDLE_HEAD_YAW_AMPLITUDE,
        speakingGesture: 0,
      };
  }
}

export function getIdleMotionTargets(
  elapsed: number,
  weightShift: number,
  motionEnabled: boolean,
): IdleMotionTargets {
  if (!motionEnabled) return { armSway: 0, shoulderSway: 0, weightShift: 0 };

  return {
    armSway:
      Math.sin(elapsed * IDLE_ARM_SWAY_FREQUENCY + IDLE_ARM_SWAY_PHASE) * IDLE_ARM_SWAY_AMPLITUDE,
    shoulderSway: Math.sin(elapsed * IDLE_SHOULDER_SWAY_FREQUENCY) * IDLE_SHOULDER_SWAY_AMPLITUDE,
    weightShift,
  };
}

function createBreathingRig(vrm: VRM): BreathingRig {
  const fingers: FingerPose[] = [];
  for (const config of FINGER_POSE_CONFIGS) {
    for (const { bones, side } of [
      { bones: config.leftBones, side: 1 },
      { bones: config.rightBones, side: -1 },
    ] as const) {
      bones.forEach((boneName, index) => {
        const bone = getPoseBone(vrm, boneName);
        const curlFactor = config.segmentCurlFactors[index];
        if (bone && curlFactor !== undefined) {
          fingers.push({ bone, bendAngle: config.bendAngle * curlFactor, side });
        }
      });
    }
  }

  return {
    chest: getPoseBone(vrm, "upperChest") ?? getPoseBone(vrm, "chest"),
    fingers,
    head: getPoseBone(vrm, "head"),
    hips: getPoseBone(vrm, "hips"),
    leftHand: getPoseBone(vrm, "leftHand"),
    leftLowerArm: getPoseBone(vrm, "leftLowerArm"),
    leftShoulder: getPoseBone(vrm, "leftShoulder"),
    leftUpperArm: getPoseBone(vrm, "leftUpperArm"),
    neck: getPoseBone(vrm, "neck"),
    rightHand: getPoseBone(vrm, "rightHand"),
    rightLowerArm: getPoseBone(vrm, "rightLowerArm"),
    rightShoulder: getPoseBone(vrm, "rightShoulder"),
    rightUpperArm: getPoseBone(vrm, "rightUpperArm"),
    spine: getPoseBone(vrm, "spine"),
    elapsed: 0,
    smoothedArmRelaxAngle: 0,
    smoothedArmSway: 0,
    smoothedBreathing: 0,
    smoothedElbowFlex: 0,
    smoothedFingerCurl: 0,
    smoothedHeadPitch: 0,
    smoothedHeadTilt: 0,
    smoothedHeadYaw: 0,
    smoothedShoulderSway: 0,
    smoothedSpeakingGesture: 0,
    smoothedWeightShift: 0,
    smoothedWristFlex: 0,
    weightShift: createWeightShiftState(),
    scratchEuler: new Euler(0, 0, 0, "XYZ"),
    scratchQuaternion: new Quaternion(),
  };
}

function getPoseBone(vrm: VRM, name: VRMHumanBoneName): PoseBone | null {
  const node = vrm.humanoid?.getNormalizedBoneNode(name) ?? null;
  return node ? { node, baseRotation: node.quaternion.clone() } : null;
}

function applyBoneRotation(
  bone: PoseBone | null,
  x: number,
  y: number,
  z: number,
  rig: BreathingRig,
): void {
  if (!bone) return;
  rig.scratchEuler.set(x, y, z, "XYZ");
  rig.scratchQuaternion.setFromEuler(rig.scratchEuler);
  bone.node.quaternion.copy(bone.baseRotation).multiply(rig.scratchQuaternion);
}

function restoreBreathingRig(rig: BreathingRig): void {
  const bones: (PoseBone | null)[] = [
    rig.chest,
    rig.head,
    rig.hips,
    rig.leftHand,
    rig.leftLowerArm,
    rig.leftShoulder,
    rig.leftUpperArm,
    rig.neck,
    rig.rightHand,
    rig.rightLowerArm,
    rig.rightShoulder,
    rig.rightUpperArm,
    rig.spine,
    ...rig.fingers.map((finger) => finger.bone),
  ];
  for (const bone of bones) {
    if (bone) bone.node.quaternion.copy(bone.baseRotation);
  }
}

function createWeightShiftState(): WeightShiftState {
  return {
    direction: 1,
    duration: 0,
    elapsed: 0,
    waiting: randomBetween(WEIGHT_SHIFT_START_MIN_SECONDS, WEIGHT_SHIFT_START_MAX_SECONDS),
  };
}

function nextWeightShiftAmount(
  shift: WeightShiftState,
  delta: number,
  motionEnabled: boolean,
): number {
  if (!motionEnabled) {
    shift.elapsed = 0;
    shift.duration = 0;
    shift.waiting = Math.max(shift.waiting, WEIGHT_SHIFT_RESUME_DELAY_SECONDS);
    return 0;
  }

  if (shift.duration === 0) {
    shift.waiting -= delta;
    if (shift.waiting > 0) return 0;
    shift.elapsed = 0;
    shift.duration = randomBetween(
      WEIGHT_SHIFT_DURATION_MIN_SECONDS,
      WEIGHT_SHIFT_DURATION_MAX_SECONDS,
    );
    shift.direction = Math.random() < 0.5 ? -1 : 1;
  }

  shift.elapsed += delta;
  const progress = Math.min(shift.elapsed / shift.duration, 1);
  if (progress >= 1) {
    shift.elapsed = 0;
    shift.duration = 0;
    shift.waiting = randomBetween(WEIGHT_SHIFT_REST_MIN_SECONDS, WEIGHT_SHIFT_REST_MAX_SECONDS);
    return 0;
  }

  return shift.direction * WEIGHT_SHIFT_MAX_ANGLE * Math.sin(Math.PI * smoothStep(progress));
}

function nextBlinkAmount(blink: BlinkState, delta: number): number {
  if (blink.waiting > 0) {
    const waitBeforeFrame = blink.waiting;
    blink.waiting = Math.max(0, blink.waiting - delta);
    if (blink.waiting > 0) return 0;
    blink.elapsed += Math.max(0, delta - waitBeforeFrame);
  } else {
    blink.elapsed += delta;
  }

  if (blink.elapsed >= BLINK_DURATION_SECONDS) {
    blink.elapsed = 0;
    blink.waiting = randomBlinkInterval();
    return 0;
  }

  return Math.sin((blink.elapsed / BLINK_DURATION_SECONDS) * Math.PI);
}

function randomBlinkInterval(): number {
  return BLINK_MIN_INTERVAL_SECONDS + Math.random() * BLINK_INTERVAL_VARIANCE_SECONDS;
}

function randomBetween(minimum: number, maximum: number): number {
  return minimum + Math.random() * (maximum - minimum);
}

function smoothStep(value: number): number {
  const clamped = Math.min(1, Math.max(0, value));
  return clamped * clamped * (3 - 2 * clamped);
}
