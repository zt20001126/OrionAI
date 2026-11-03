import { PlatformIcon } from "../platform/PlatformIcon";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { useMembershipStatus } from "./MembershipStatusContext";
import { t } from "../../i18n/localeStore";

import "./MembershipEntry.css";

interface MembershipEntryProps {
  onNavigate: (path: PlatformRoute) => void;
  variant?: "default" | "sidebar";
}

export function MembershipEntry({ onNavigate, variant = "default" }: MembershipEntryProps) {
  const { overview, isLoading, error } = useMembershipStatus();
  const isActive = Boolean(overview?.active_period);
  const statusLabel = t(isActive ? "VIP 会员" : isLoading || error ? "会员中心" : "开通会员");
  const label = variant === "sidebar" ? t("会员中心") : statusLabel;

  return (
    <button
      aria-label={label}
      className={`membership-entry${variant === "sidebar" ? " membership-entry--sidebar" : ""}`}
      data-tooltip={variant === "sidebar" ? label : undefined}
      onClick={() => onNavigate(platformPaths.membership)}
      type="button"
    >
      <PlatformIcon name="crown" size={variant === "sidebar" ? 18 : 14} />
      <span>{label}</span>
    </button>
  );
}
