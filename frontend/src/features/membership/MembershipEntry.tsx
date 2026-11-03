import { useEffect, useState } from "react";

import { PlatformIcon } from "../platform/PlatformIcon";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { useMembershipStatus } from "./MembershipStatusContext";
import { t } from "../../i18n/localeStore";

import "./MembershipEntry.css";

const MAX_TIMEOUT_MS = 2_147_483_647;

interface MembershipEntryProps {
  onNavigate: (path: PlatformRoute) => void;
  variant?: "default" | "sidebar";
}

export function MembershipEntry({ onNavigate, variant = "default" }: MembershipEntryProps) {
  const { overview, isLoading, error, refresh } = useMembershipStatus();
  const [membershipClock, setMembershipClock] = useState(Date.now);
  const activePeriod = overview?.active_period ?? null;
  const expiresAt = activePeriod ? Date.parse(activePeriod.expires_at) : null;
  const isActive = Boolean(overview?.active_period);
  const isCurrentlyActive = expiresAt !== null && expiresAt > membershipClock;
  const statusLabel = t(isActive ? "VIP 会员" : isLoading || error ? "会员中心" : "开通会员");
  const label = variant === "sidebar" ? t("会员中心") : statusLabel;

  useEffect(() => {
    const expiration = expiresAt ?? Number.NaN;
    if (!Number.isFinite(expiration)) return;

    let timeoutId: number | undefined;
    function updateAtExpiry() {
      const remaining = expiration - Date.now();
      if (remaining <= 0) {
        setMembershipClock(Date.now());
        void refresh().catch(() => undefined);
        return;
      }
      timeoutId = window.setTimeout(updateAtExpiry, Math.min(remaining, MAX_TIMEOUT_MS));
    }

    updateAtExpiry();
    return () => {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
    };
  }, [expiresAt, refresh]);

  return (
    <button
      aria-label={label}
      className={`membership-entry${variant === "sidebar" ? " membership-entry--sidebar" : ""}${isCurrentlyActive ? " is-member" : ""}`}
      data-tooltip={variant === "sidebar" ? label : undefined}
      onClick={() => onNavigate(platformPaths.membership)}
      type="button"
    >
      <PlatformIcon name="crown" size={variant === "sidebar" ? 18 : 14} />
      <span>{label}</span>
    </button>
  );
}
