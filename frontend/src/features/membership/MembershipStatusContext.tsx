import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { getMembershipOverview } from "./membershipApi";
import type { MembershipOverview } from "./types";
import { t } from "../../i18n/localeStore";

interface MembershipStatusValue {
  overview: MembershipOverview | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<MembershipOverview | null>;
}

const MembershipStatusContext = createContext<MembershipStatusValue | null>(null);

export function MembershipStatusProvider({
  children,
  isGuest,
}: {
  children: ReactNode;
  isGuest: boolean;
}) {
  const [overview, setOverview] = useState<MembershipOverview | null>(null);
  const [isLoading, setIsLoading] = useState(!isGuest);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (isGuest) {
      setOverview(null);
      setIsLoading(false);
      setError(null);
      return null;
    }

    setIsLoading(true);
    setError(null);
    try {
      const nextOverview = await getMembershipOverview();
      setOverview(nextOverview);
      return nextOverview;
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : t("会员信息暂时无法加载。");
      setError(message);
      throw cause;
    } finally {
      setIsLoading(false);
    }
  }, [isGuest]);

  useEffect(() => {
    if (isGuest) return;
    let active = true;
    void getMembershipOverview()
      .then((nextOverview) => {
        if (active) {
          setOverview(nextOverview);
          setError(null);
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof Error ? cause.message : t("会员信息暂时无法加载。"));
        }
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [isGuest]);

  useEffect(() => {
    if (isGuest) return;
    function refreshWhenVisible() {
      if (document.visibilityState === "visible") void refresh().catch(() => undefined);
    }
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [isGuest, refresh]);

  const value = useMemo(
    () => ({ overview, isLoading, error, refresh }),
    [overview, isLoading, error, refresh],
  );

  return (
    <MembershipStatusContext.Provider value={value}>{children}</MembershipStatusContext.Provider>
  );
}

export function useMembershipStatus(): MembershipStatusValue {
  const context = useContext(MembershipStatusContext);
  if (!context) throw new Error("useMembershipStatus 必须在 MembershipStatusProvider 内使用。");
  return context;
}
