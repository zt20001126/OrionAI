import { VRMExpressionPresetName, type VRM } from "@pixiv/three-vrm";

/** Return whether this VRM exposes at least one expression usable for mouth motion. */
export function hasVrmMouthExpression(vrm: VRM): boolean {
  const manager = vrm.expressionManager;
  return Boolean(
    manager?.getExpression(VRMExpressionPresetName.Aa) ||
    manager?.getExpression(VRMExpressionPresetName.Oh),
  );
}
