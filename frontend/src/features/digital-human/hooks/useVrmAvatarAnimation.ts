import { useCallback, useEffect, useRef } from "react";
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
const IDLE_BLINK_MIN_INTERVAL_SECONDS = 2.2;
const IDLE_BLINK_INTERVAL_VARIANCE_SECONDS = 2.1;
const IDLE_BLINK_BLEND_SPEED = 48;
const ARM_RELAX_ANGLE = 1.25;
const SHOULDER_RELAX_SHARE = 0.12;
// Orion 的 normalized 肘骨绕局部 Z 轴才会在正面形成屈肘；Y 轴主要让前臂转向深度方向。
const LEFT_ELBOW_FLEX_ANGLE = 0.18;
const RIGHT_ELBOW_FLEX_ANGLE = 0.21;
const LEFT_WRIST_FLEX_ANGLE = 0.045;
const RIGHT_WRIST_FLEX_ANGLE = 0.06;
const POSE_BLEND_SPEED = 4;
const CHEST_BREATHING_AMPLITUDE = 0.022;
const CHEST_BREATHING_FREQUENCY = 0.9;
const IDLE_CHEST_BREATHING_AMPLITUDE = 0.035;
const IDLE_CHEST_BREATHING_FREQUENCY = 1.15;
const IDLE_HEAD_PITCH_AMPLITUDE = 0.085;
const IDLE_HEAD_YAW_AMPLITUDE = 0.07;
const IDLE_HEAD_TILT_AMPLITUDE = 0.085;
const IDLE_HEAD_PITCH_FREQUENCY = 0.6;
const IDLE_HEAD_YAW_FREQUENCY = 0.34;
const IDLE_HEAD_TILT_FREQUENCY = 0.42;
const NECK_MOTION_SHARE = 0.24;
const POINTER_HEAD_PITCH_AMPLITUDE = 0.34;
const POINTER_HEAD_YAW_AMPLITUDE = 0.62;
const IDLE_SHOULDER_SWAY_AMPLITUDE = 0.018;
const IDLE_SHOULDER_SWAY_FREQUENCY = 0.55;
const IDLE_SHOULDER_BREATHING_AMPLITUDE = 0.019;
const IDLE_ARM_SWAY_AMPLITUDE = 0.018;
const IDLE_ARM_SWAY_FREQUENCY = 0.45;
const IDLE_ARM_SWAY_PHASE = 0.7;
const IDLE_RIGHT_ARM_SWAY_PHASE = 2.5;
const WEIGHT_SHIFT_MAX_ANGLE = 0.038;
const WEIGHT_SHIFT_START_MIN_SECONDS = 3.5;
const WEIGHT_SHIFT_START_MAX_SECONDS = 6;
const WEIGHT_SHIFT_DURATION_MIN_SECONDS = 2.8;
const WEIGHT_SHIFT_DURATION_MAX_SECONDS = 3.8;
const WEIGHT_SHIFT_REST_MIN_SECONDS = 4;
const WEIGHT_SHIFT_REST_MAX_SECONDS = 7;
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
const WAVE_DURATION_SECONDS = 2;
const WAVE_RAISE_SECONDS = 0.4;
const WAVE_SWING_SECONDS = 1.2;
const WAVE_CYCLES = 3;
const WAVE_RAISE_ANGLE = 2.42;
const WAVE_SHOULDER_RAISE_ANGLE = 0.16;
const WAVE_ELBOW_SWING_ANGLE = 0.48;
const WAVE_HAND_SWING_ANGLE = 0.3;
const HEAD_TILT_DURATION_SECONDS = 1.8;
const HEAD_TILT_ENTRY_SECONDS = 0.22;
const HEAD_TILT_HOLD_SECONDS = 0.98;
const HEAD_TILT_RELEASE_SECONDS = 0.6;
const HEAD_TILT_ANGLE = 0.4;
const HAPPY_DURATION_SECONDS = 2;
const HAPPY_BLEND_SECONDS = 0.22;
const HAPPY_RELEASE_SECONDS = 0.35;
const HAPPY_NOD_START_SECONDS = 0.25;
const HAPPY_NOD_DURATION_SECONDS = 1.3;
const HAPPY_NOD_CYCLES = 2;
const HAPPY_NOD_AMPLITUDE = 0.22;
const HAPPY_ARM_RAISE_ANGLE = 1.18;
const HAPPY_ELBOW_BEND_ANGLE = 0.16;
const HAPPY_BODY_SWAY_ANGLE = 0.05;
const HAPPY_EXPRESSION_WEIGHT = 0.92;
const GESTURE_EXPRESSION_BLEND_SPEED = 14;
const MAX_GESTURE_ARM_ANGLE = 2.55;
const MAX_GESTURE_FOREARM_ANGLE = 0.82;
const MAX_GESTURE_HEAD_TILT = 0.48;
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
  smoothedRightArmSway: number;
  smoothedBreathing: number;
  smoothedLeftElbowFlex: number;
  smoothedRightElbowFlex: number;
  smoothedFingerCurl: number;
  smoothedHeadPitch: number;
  smoothedHeadTilt: number;
  smoothedHeadYaw: number;
  smoothedShoulderSway: number;
  smoothedShoulderBreathing: number;
  smoothedSpeakingGesture: number;
  smoothedWeightShift: number;
  smoothedLeftWristFlex: number;
  smoothedRightWristFlex: number;
  weightShift: WeightShiftState;
  scratchBlendedQuaternion: Quaternion;
  scratchEuler: Euler;
  scratchGestureEuler: Euler;
  scratchGestureQuaternion: Quaternion;
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
  rightArmSway: number;
  shoulderBreathing: number;
  shoulderSway: number;
  weightShift: number;
}

export interface IdleArmPoseOffsets {
  leftElbow: { x: number; y: number; z: number };
  leftWrist: { x: number; y: number; z: number };
  rightElbow: { x: number; y: number; z: number };
  rightWrist: { x: number; y: number; z: number };
}

const IDLE_ARM_POSE_OFFSETS: IdleArmPoseOffsets = {
  leftElbow: { x: 0, y: 0, z: LEFT_ELBOW_FLEX_ANGLE },
  leftWrist: { x: 0, y: 0, z: LEFT_WRIST_FLEX_ANGLE },
  rightElbow: { x: 0, y: 0, z: -RIGHT_ELBOW_FLEX_ANGLE },
  rightWrist: { x: 0, y: 0, z: -RIGHT_WRIST_FLEX_ANGLE },
};

export type VrmAvatarGesture = "wave" | "headTilt" | "happy";

export type VrmAvatarGesturePlayer = (gesture: VrmAvatarGesture) => boolean;

export interface VrmAvatarGestureState {
  direction: 1 | -1;
  elapsed: number;
  kind: VrmAvatarGesture;
}

export interface VrmAvatarGestureTargets {
  armBlend: number;
  chestRoll: number;
  expressionWeight: number;
  headBlend: number;
  headPitch: number;
  headTilt: number;
  headYaw: number;
  leftArmBlend: number;
  leftShoulderRaise: number;
  leftUpperArmRaise: number;
  rightArmBlend: number;
  rightElbowBend: number;
  rightElbowWave: number;
  rightHandWave: number;
  rightShoulderRaise: number;
  rightUpperArmRaise: number;
  spineRoll: number;
}

const NEUTRAL_GESTURE_TARGETS: VrmAvatarGestureTargets = {
  armBlend: 0,
  chestRoll: 0,
  expressionWeight: 0,
  headBlend: 0,
  headPitch: 0,
  headTilt: 0,
  headYaw: 0,
  leftArmBlend: 0,
  leftShoulderRaise: 0,
  leftUpperArmRaise: 0,
  rightArmBlend: 0,
  rightElbowBend: 0,
  rightElbowWave: 0,
  rightHandWave: 0,
  rightShoulderRaise: 0,
  rightUpperArmRaise: 0,
  spineRoll: 0,
};

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
): VrmAvatarGesturePlayer {
  const blinkState = useRef<BlinkState>({
    elapsed: 0,
    waiting: randomBlinkInterval(status === "idle"),
  });
  const smoothedBlink = useRef(0);
  const prefersReducedMotion = useRef(false);
  const breathingRig = useRef<BreathingRig | null>(null);
  const smoothedMouth = useRef(0);
  const smoothedGestureExpression = useRef(0);
  const gestureState = useRef<VrmAvatarGestureState | null>(null);
  const nextHeadTiltDirection = useRef<1 | -1>(1);

  const playGesture = useCallback<VrmAvatarGesturePlayer>((kind) => {
    if (gestureState.current) return false;

    const direction = kind === "headTilt" ? nextHeadTiltDirection.current : 1;
    if (kind === "headTilt") nextHeadTiltDirection.current *= -1;
    gestureState.current = { direction, elapsed: 0, kind };
    return true;
  }, []);

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
      for (const expression of [VRMExpressionPresetName.Happy, VRMExpressionPresetName.Relaxed]) {
        if (manager?.getExpression(expression)) manager.setValue(expression, 0);
      }
    },
    [vrm],
  );

  useFrame((_, delta) => {
    const activeGesture = gestureState.current;
    let gestureTargets = NEUTRAL_GESTURE_TARGETS;
    if (activeGesture) {
      activeGesture.elapsed = Math.min(
        getVrmAvatarGestureDuration(activeGesture.kind),
        activeGesture.elapsed + delta,
      );
      gestureTargets = getVrmAvatarGestureTargets(activeGesture);
      if (activeGesture.elapsed >= getVrmAvatarGestureDuration(activeGesture.kind)) {
        gestureState.current = null;
      }
    }

    const manager = vrm.expressionManager;
    const motionEnabled = !prefersReducedMotion.current;
    const blinkAmount = nextBlinkAmount(blinkState.current, delta, status === "idle");
    const blinkTarget = motionEnabled ? blinkAmount : 0;
    const blinkBlendSpeed = status === "idle" ? IDLE_BLINK_BLEND_SPEED : BLINK_BLEND_SPEED;
    const blinkBlend = 1 - Math.exp(-blinkBlendSpeed * delta);
    smoothedBlink.current += (blinkTarget - smoothedBlink.current) * blinkBlend;

    if (manager?.getExpression(VRMExpressionPresetName.Blink)) {
      manager.setValue(VRMExpressionPresetName.Blink, smoothedBlink.current);
    }

    const mouthExpression = MOUTH_EXPRESSIONS.find((name) => manager?.getExpression(name));
    const targetMouth = status === "speaking" ? Math.min(1, Math.max(0, mouthOpen)) : 0;
    smoothedMouth.current += (targetMouth - smoothedMouth.current) * Math.min(1, delta * 14);
    if (mouthExpression) manager?.setValue(mouthExpression, smoothedMouth.current);

    const expressionTarget = gestureTargets.expressionWeight;
    const expressionBlend = 1 - Math.exp(-GESTURE_EXPRESSION_BLEND_SPEED * delta);
    smoothedGestureExpression.current +=
      (expressionTarget - smoothedGestureExpression.current) * expressionBlend;
    const happyExpression = manager?.getExpression(VRMExpressionPresetName.Happy)
      ? VRMExpressionPresetName.Happy
      : manager?.getExpression(VRMExpressionPresetName.Relaxed)
        ? VRMExpressionPresetName.Relaxed
        : null;
    if (manager?.getExpression(VRMExpressionPresetName.Happy)) {
      manager.setValue(
        VRMExpressionPresetName.Happy,
        happyExpression === VRMExpressionPresetName.Happy ? smoothedGestureExpression.current : 0,
      );
    }
    if (manager?.getExpression(VRMExpressionPresetName.Relaxed)) {
      manager.setValue(
        VRMExpressionPresetName.Relaxed,
        happyExpression === VRMExpressionPresetName.Relaxed ? smoothedGestureExpression.current : 0,
      );
    }

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
    // 待机时加强呼吸，其余状态保留原有节奏，避免影响说话和倾听表现。
    const breathingFrequency =
      status === "idle" ? IDLE_CHEST_BREATHING_FREQUENCY : CHEST_BREATHING_FREQUENCY;
    const breathingAmplitude =
      status === "idle" ? IDLE_CHEST_BREATHING_AMPLITUDE : CHEST_BREATHING_AMPLITUDE;
    const breathingTarget = motionEnabled
      ? Math.sin(rig.elapsed * breathingFrequency) * breathingAmplitude
      : 0;
    const blend = 1 - Math.exp(-POSE_BLEND_SPEED * delta);

    rig.smoothedArmRelaxAngle += (ARM_RELAX_ANGLE - rig.smoothedArmRelaxAngle) * blend;
    rig.smoothedArmSway += (idleTargets.armSway - rig.smoothedArmSway) * blend;
    rig.smoothedRightArmSway += (idleTargets.rightArmSway - rig.smoothedRightArmSway) * blend;
    rig.smoothedBreathing += (breathingTarget - rig.smoothedBreathing) * blend;
    const idleArmPose = getIdleArmPoseOffsets();
    rig.smoothedLeftElbowFlex += (idleArmPose.leftElbow.z - rig.smoothedLeftElbowFlex) * blend;
    rig.smoothedRightElbowFlex += (idleArmPose.rightElbow.z - rig.smoothedRightElbowFlex) * blend;
    rig.smoothedFingerCurl += (1 - rig.smoothedFingerCurl) * blend;
    rig.smoothedHeadPitch += (statusTargets.headPitch - rig.smoothedHeadPitch) * blend;
    rig.smoothedHeadTilt += (statusTargets.headTilt - rig.smoothedHeadTilt) * blend;
    rig.smoothedHeadYaw += (statusTargets.headYaw - rig.smoothedHeadYaw) * blend;
    rig.smoothedShoulderSway += (idleTargets.shoulderSway - rig.smoothedShoulderSway) * blend;
    rig.smoothedShoulderBreathing +=
      (idleTargets.shoulderBreathing - rig.smoothedShoulderBreathing) * blend;
    rig.smoothedSpeakingGesture +=
      (statusTargets.speakingGesture - rig.smoothedSpeakingGesture) * blend;
    rig.smoothedWeightShift += (idleTargets.weightShift - rig.smoothedWeightShift) * blend;
    rig.smoothedLeftWristFlex += (idleArmPose.leftWrist.z - rig.smoothedLeftWristFlex) * blend;
    rig.smoothedRightWristFlex += (idleArmPose.rightWrist.z - rig.smoothedRightWristFlex) * blend;

    const shoulderRelax = rig.smoothedArmRelaxAngle * SHOULDER_RELAX_SHARE;
    const upperArmRelax = rig.smoothedArmRelaxAngle * (1 - SHOULDER_RELAX_SHARE);
    const leftShoulderSway = rig.smoothedShoulderSway;
    const armBlend = gestureTargets.armBlend;
    const leftArmBlend = gestureTargets.leftArmBlend;
    const rightArmBlend = gestureTargets.rightArmBlend;
    const headBlend = gestureTargets.headBlend;
    const remainingHeadMotion = 1 - headBlend;
    const ambientHeadPitch = rig.smoothedHeadPitch * remainingHeadMotion;
    const ambientHeadYaw = rig.smoothedHeadYaw * remainingHeadMotion;
    const ambientHeadTilt = rig.smoothedHeadTilt * remainingHeadMotion;
    const speakingGesture = rig.smoothedSpeakingGesture * (1 - rightArmBlend);

    applyBoneRotation(rig.hips, 0, 0, rig.smoothedWeightShift, rig);
    applyMixedBoneRotation(
      rig.spine,
      0,
      0,
      -rig.smoothedWeightShift * SPINE_COUNTER_SHIFT_SHARE,
      0,
      0,
      clampGestureAngle(
        -rig.smoothedWeightShift * SPINE_COUNTER_SHIFT_SHARE + gestureTargets.spineRoll,
        MAX_GESTURE_HEAD_TILT,
      ),
      armBlend,
      rig,
    );
    applyMixedBoneRotation(
      rig.chest,
      rig.smoothedBreathing,
      0,
      0,
      rig.smoothedBreathing,
      0,
      clampGestureAngle(gestureTargets.chestRoll, MAX_GESTURE_HEAD_TILT),
      armBlend,
      rig,
    );
    applyMixedBoneRotation(
      rig.neck,
      ambientHeadPitch * NECK_MOTION_SHARE,
      ambientHeadYaw * NECK_MOTION_SHARE,
      ambientHeadTilt * NECK_MOTION_SHARE,
      ambientHeadPitch * NECK_MOTION_SHARE + gestureTargets.headPitch * NECK_MOTION_SHARE,
      ambientHeadYaw * NECK_MOTION_SHARE + gestureTargets.headYaw * NECK_MOTION_SHARE,
      clampGestureAngle(
        ambientHeadTilt * NECK_MOTION_SHARE + gestureTargets.headTilt * NECK_MOTION_SHARE,
        MAX_GESTURE_HEAD_TILT,
      ),
      headBlend,
      rig,
    );
    applyMixedBoneRotation(
      rig.head,
      ambientHeadPitch * (1 - NECK_MOTION_SHARE),
      ambientHeadYaw * (1 - NECK_MOTION_SHARE),
      ambientHeadTilt * (1 - NECK_MOTION_SHARE),
      ambientHeadPitch * (1 - NECK_MOTION_SHARE) +
        gestureTargets.headPitch * (1 - NECK_MOTION_SHARE),
      ambientHeadYaw * (1 - NECK_MOTION_SHARE) + gestureTargets.headYaw * (1 - NECK_MOTION_SHARE),
      clampGestureAngle(
        ambientHeadTilt * (1 - NECK_MOTION_SHARE) +
          gestureTargets.headTilt * (1 - NECK_MOTION_SHARE),
        MAX_GESTURE_HEAD_TILT,
      ),
      headBlend,
      rig,
    );
    applyMixedBoneRotation(
      rig.leftShoulder,
      0,
      0,
      shoulderRelax + leftShoulderSway - rig.smoothedShoulderBreathing,
      0,
      0,
      clampGestureAngle(
        shoulderRelax +
          leftShoulderSway -
          rig.smoothedShoulderBreathing +
          gestureTargets.leftShoulderRaise,
        MAX_GESTURE_ARM_ANGLE,
      ),
      leftArmBlend,
      rig,
    );
    applyMixedBoneRotation(
      rig.rightShoulder,
      0,
      0,
      -(shoulderRelax + leftShoulderSway) + rig.smoothedShoulderBreathing,
      0,
      0,
      clampGestureAngle(
        -(shoulderRelax + leftShoulderSway) +
          rig.smoothedShoulderBreathing +
          gestureTargets.rightShoulderRaise,
        MAX_GESTURE_ARM_ANGLE,
      ),
      rightArmBlend,
      rig,
    );
    applyMixedBoneRotation(
      rig.leftUpperArm,
      0,
      0,
      upperArmRelax + rig.smoothedArmSway,
      0,
      0,
      clampGestureAngle(
        upperArmRelax + rig.smoothedArmSway + gestureTargets.leftUpperArmRaise,
        MAX_GESTURE_ARM_ANGLE,
      ),
      leftArmBlend,
      rig,
    );
    applyMixedBoneRotation(
      rig.rightUpperArm,
      0,
      0,
      -(upperArmRelax + rig.smoothedRightArmSway) + speakingGesture,
      0,
      0,
      clampGestureAngle(
        -(upperArmRelax + rig.smoothedRightArmSway) +
          speakingGesture +
          gestureTargets.rightUpperArmRaise,
        MAX_GESTURE_ARM_ANGLE,
      ),
      rightArmBlend,
      rig,
    );
    applyBoneRotation(
      rig.leftLowerArm,
      idleArmPose.leftElbow.x,
      idleArmPose.leftElbow.y,
      rig.smoothedLeftElbowFlex,
      rig,
    );
    applyMixedBoneRotation(
      rig.rightLowerArm,
      0,
      0,
      rig.smoothedRightElbowFlex,
      idleArmPose.rightElbow.x,
      idleArmPose.rightElbow.y,
      rig.smoothedRightElbowFlex +
        clampGestureAngle(
          gestureTargets.rightElbowBend + gestureTargets.rightElbowWave,
          MAX_GESTURE_FOREARM_ANGLE,
        ),
      rightArmBlend,
      rig,
    );
    applyBoneRotation(
      rig.leftHand,
      idleArmPose.leftWrist.x,
      idleArmPose.leftWrist.y,
      rig.smoothedLeftWristFlex,
      rig,
    );
    applyMixedBoneRotation(
      rig.rightHand,
      0,
      0,
      rig.smoothedRightWristFlex,
      idleArmPose.rightWrist.x,
      idleArmPose.rightWrist.y,
      rig.smoothedRightWristFlex +
        clampGestureAngle(gestureTargets.rightHandWave, MAX_GESTURE_HEAD_TILT),
      rightArmBlend,
      rig,
    );

    for (const finger of rig.fingers) {
      const fingerArmBlend = finger.side === 1 ? leftArmBlend : rightArmBlend;
      applyBoneRotation(
        finger.bone,
        0,
        finger.side * finger.bendAngle * rig.smoothedFingerCurl * (1 - fingerArmBlend * 0.82),
        0,
        rig,
      );
    }

    vrm.update(delta);
  });

  return playGesture;
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
  if (!motionEnabled) {
    return { armSway: 0, rightArmSway: 0, shoulderBreathing: 0, shoulderSway: 0, weightShift: 0 };
  }

  return {
    armSway:
      Math.sin(elapsed * IDLE_ARM_SWAY_FREQUENCY + IDLE_ARM_SWAY_PHASE) * IDLE_ARM_SWAY_AMPLITUDE,
    rightArmSway:
      Math.sin(elapsed * IDLE_ARM_SWAY_FREQUENCY + IDLE_RIGHT_ARM_SWAY_PHASE) *
      IDLE_ARM_SWAY_AMPLITUDE,
    shoulderBreathing:
      Math.sin(elapsed * IDLE_CHEST_BREATHING_FREQUENCY) * IDLE_SHOULDER_BREATHING_AMPLITUDE,
    shoulderSway: Math.sin(elapsed * IDLE_SHOULDER_SWAY_FREQUENCY) * IDLE_SHOULDER_SWAY_AMPLITUDE,
    weightShift,
  };
}

export function getIdleArmPoseOffsets(): IdleArmPoseOffsets {
  return IDLE_ARM_POSE_OFFSETS;
}

export function getVrmAvatarGestureDuration(gesture: VrmAvatarGesture): number {
  switch (gesture) {
    case "wave":
      return WAVE_DURATION_SECONDS;
    case "headTilt":
      return HEAD_TILT_DURATION_SECONDS;
    case "happy":
      return HAPPY_DURATION_SECONDS;
  }
}

export function getVrmAvatarGestureTargets(state: VrmAvatarGestureState): VrmAvatarGestureTargets {
  const elapsed = Math.min(getVrmAvatarGestureDuration(state.kind), Math.max(0, state.elapsed));

  switch (state.kind) {
    case "wave": {
      const raise = Math.min(
        smoothStep(elapsed / WAVE_RAISE_SECONDS),
        1 - smoothStep((elapsed - WAVE_RAISE_SECONDS - WAVE_SWING_SECONDS) / WAVE_RAISE_SECONDS),
      );
      const swingProgress = clampProgress((elapsed - WAVE_RAISE_SECONDS) / WAVE_SWING_SECONDS);
      const swing = Math.sin(swingProgress * Math.PI * 2 * WAVE_CYCLES);

      return {
        ...NEUTRAL_GESTURE_TARGETS,
        armBlend: raise,
        chestRoll: -0.035,
        // 挥手只接管右臂，左臂继续保持待机姿态。
        rightArmBlend: raise,
        rightElbowWave: 0.2 + swing * WAVE_ELBOW_SWING_ANGLE,
        rightHandWave: swing * WAVE_HAND_SWING_ANGLE,
        rightShoulderRaise: WAVE_SHOULDER_RAISE_ANGLE,
        rightUpperArmRaise: WAVE_RAISE_ANGLE,
        spineRoll: -0.035,
      };
    }
    case "headTilt": {
      const enter = smoothStep(elapsed / HEAD_TILT_ENTRY_SECONDS);
      const releaseStart = HEAD_TILT_ENTRY_SECONDS + HEAD_TILT_HOLD_SECONDS;
      const release = 1 - smoothStep((elapsed - releaseStart) / HEAD_TILT_RELEASE_SECONDS);
      const headBlend = enter * release;

      return {
        ...NEUTRAL_GESTURE_TARGETS,
        expressionWeight: headBlend * 0.22,
        headBlend,
        headTilt: state.direction * HEAD_TILT_ANGLE,
      };
    }
    case "happy": {
      const blend =
        smoothStep(elapsed / HAPPY_BLEND_SECONDS) *
        (1 -
          smoothStep(
            (elapsed - HAPPY_DURATION_SECONDS + HAPPY_RELEASE_SECONDS) / HAPPY_RELEASE_SECONDS,
          ));
      const nodProgress = clampProgress(
        (elapsed - HAPPY_NOD_START_SECONDS) / HAPPY_NOD_DURATION_SECONDS,
      );
      const swayProgress = clampProgress(
        (elapsed - HAPPY_NOD_START_SECONDS) / HAPPY_NOD_DURATION_SECONDS,
      );
      const nod = Math.sin(nodProgress * Math.PI * 2 * HAPPY_NOD_CYCLES) * HAPPY_NOD_AMPLITUDE;
      const bodySway =
        Math.sin(swayProgress * Math.PI * 2 * HAPPY_NOD_CYCLES) * HAPPY_BODY_SWAY_ANGLE;

      return {
        ...NEUTRAL_GESTURE_TARGETS,
        armBlend: blend,
        chestRoll: bodySway * 0.65,
        expressionWeight: blend * HAPPY_EXPRESSION_WEIGHT,
        headBlend: blend,
        headPitch: nod,
        leftArmBlend: blend,
        leftShoulderRaise: -0.12,
        leftUpperArmRaise: -HAPPY_ARM_RAISE_ANGLE,
        rightArmBlend: blend,
        rightElbowBend: HAPPY_ELBOW_BEND_ANGLE,
        rightShoulderRaise: 0.12,
        rightUpperArmRaise: HAPPY_ARM_RAISE_ANGLE,
        spineRoll: bodySway,
      };
    }
  }
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
    smoothedRightArmSway: 0,
    smoothedBreathing: 0,
    smoothedLeftElbowFlex: 0,
    smoothedRightElbowFlex: 0,
    smoothedFingerCurl: 0,
    smoothedHeadPitch: 0,
    smoothedHeadTilt: 0,
    smoothedHeadYaw: 0,
    smoothedShoulderSway: 0,
    smoothedShoulderBreathing: 0,
    smoothedSpeakingGesture: 0,
    smoothedWeightShift: 0,
    smoothedLeftWristFlex: 0,
    smoothedRightWristFlex: 0,
    weightShift: createWeightShiftState(),
    scratchBlendedQuaternion: new Quaternion(),
    scratchEuler: new Euler(0, 0, 0, "XYZ"),
    scratchGestureEuler: new Euler(0, 0, 0, "XYZ"),
    scratchGestureQuaternion: new Quaternion(),
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

function applyMixedBoneRotation(
  bone: PoseBone | null,
  ambientX: number,
  ambientY: number,
  ambientZ: number,
  gestureX: number,
  gestureY: number,
  gestureZ: number,
  gestureBlend: number,
  rig: BreathingRig,
): void {
  if (!bone) return;

  rig.scratchEuler.set(ambientX, ambientY, ambientZ, "XYZ");
  rig.scratchQuaternion.setFromEuler(rig.scratchEuler);
  rig.scratchGestureEuler.set(gestureX, gestureY, gestureZ, "XYZ");
  rig.scratchGestureQuaternion.setFromEuler(rig.scratchGestureEuler);
  rig.scratchBlendedQuaternion
    .copy(rig.scratchQuaternion)
    .slerp(rig.scratchGestureQuaternion, clampProgress(gestureBlend));
  bone.node.quaternion.copy(bone.baseRotation).multiply(rig.scratchBlendedQuaternion);
}

function clampGestureAngle(value: number, maximumAngle: number): number {
  return Math.max(-maximumAngle, Math.min(maximumAngle, value));
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

function nextBlinkAmount(blink: BlinkState, delta: number, isIdle: boolean): number {
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
    blink.waiting = randomBlinkInterval(isIdle);
    return 0;
  }

  return Math.sin((blink.elapsed / BLINK_DURATION_SECONDS) * Math.PI);
}

function randomBlinkInterval(isIdle: boolean): number {
  return isIdle
    ? IDLE_BLINK_MIN_INTERVAL_SECONDS + Math.random() * IDLE_BLINK_INTERVAL_VARIANCE_SECONDS
    : BLINK_MIN_INTERVAL_SECONDS + Math.random() * BLINK_INTERVAL_VARIANCE_SECONDS;
}

function randomBetween(minimum: number, maximum: number): number {
  return minimum + Math.random() * (maximum - minimum);
}

function smoothStep(value: number): number {
  const clamped = clampProgress(value);
  return clamped * clamped * (3 - 2 * clamped);
}

function clampProgress(value: number): number {
  return Math.min(1, Math.max(0, value));
}
