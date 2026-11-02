import { PlatformIcon } from "../platform/PlatformIcon";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { useMembershipStatus } from "./MembershipStatusContext";

export function MembershipEntry({ onNavigate }: { onNavigate: (path: PlatformRoute) => void }) {
  const { overview, isLoading, error } = useMembershipStatus();
  const isActive = Boolean(overview?.active_period);
  const label = isActive ? "VIP 会员" : isLoading || error ? "会员中心" : "开通会员";

  return (
    <button
      aria-label={label}
      className="membership-entry"
      onClick={() => onNavigate(platformPaths.membership)}
      type="button"
    >
      <PlatformIcon name="crown" size={14} />
      <span>{label}</span>
    </button>
  );
}
