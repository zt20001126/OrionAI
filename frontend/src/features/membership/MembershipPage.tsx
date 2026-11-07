import { useEffect, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { PlatformIcon } from "../platform/PlatformIcon";
import {
  createMembershipCheckoutPath,
  platformPaths,
  type PlatformRoute,
} from "../platform/platformData";
import { MembershipBanner } from "./components/MembershipBanner";
import { MembershipPlanCard } from "./components/MembershipPlanCard";
import { useMembershipStatus } from "./MembershipStatusContext";
import { getMembershipOrder, listMembershipPlans } from "./membershipApi";
import { getRecommendedPlanId } from "./membershipUtils";
import type { MembershipPlan } from "./types";

import "./membership.css";
import { t } from "../../i18n/localeStore";

const PAYMENT_POLL_INTERVAL_MS = 2000;
const MAX_PAYMENT_POLL_ATTEMPTS = 30;

interface MembershipPageProps {
  isGuest: boolean;
  onNavigate: (path: PlatformRoute) => void;
}

export function MembershipPage({ isGuest, onNavigate }: MembershipPageProps) {
  const {
    overview,
    isLoading: isMembershipLoading,
    error: membershipError,
    refresh,
  } = useMembershipStatus();
  const { showToast } = useToast();
  const [plans, setPlans] = useState<MembershipPlan[]>([]);
  const [arePlansLoading, setArePlansLoading] = useState(true);
  const [plansError, setPlansError] = useState<string | null>(null);
  const [plansReloadVersion, setPlansReloadVersion] = useState(0);
  const [paymentMessage, setPaymentMessage] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).has("order_id")
      ? t("正在向服务端确认支付结果…")
      : null,
  );

  useEffect(() => {
    const controller = new AbortController();
    void listMembershipPlans(controller.signal)
      .then((items) => {
        setPlans(items);
        setPlansError(null);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setPlansError(cause instanceof Error ? cause.message : t("会员套餐暂时无法加载。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setArePlansLoading(false);
      });
    return () => controller.abort();
  }, [plansReloadVersion]);

  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    const orderId = parameters.get("order_id");
    if (orderId === null) return;
    const confirmedOrderId = orderId;

    let active = true;
    let attempts = 0;
    let timer = 0;
    async function checkPayment() {
      attempts += 1;
      try {
        const order = await getMembershipOrder(confirmedOrderId);
        if (!active) return;
        if (order.status === "paid") {
          setPaymentMessage(t("支付成功，会员信息已更新。"));
          await refresh().catch(() => null);
          showToast("success", t("支付已由服务端确认，会员信息已刷新。"));
          return;
        }
        if (order.status === "failed" || order.status === "expired") {
          const message =
            order.status === "failed"
              ? t("支付未完成，可重新发起支付。")
              : t("支付链接已过期，请重新选择套餐。");
          setPaymentMessage(message);
          showToast("warning", message);
          return;
        }
      } catch {
        if (active && attempts >= MAX_PAYMENT_POLL_ATTEMPTS) {
          setPaymentMessage(t("暂未获取到支付结果，请稍后在订单记录中查看。"));
          return;
        }
      }

      if (active && attempts < MAX_PAYMENT_POLL_ATTEMPTS) {
        timer = window.setTimeout(() => void checkPayment(), PAYMENT_POLL_INTERVAL_MS);
      } else if (active) {
        setPaymentMessage(t("支付仍在处理中，你可以稍后刷新订单状态。"));
      }
    }

    void checkPayment();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [refresh, showToast]);

  const activePeriod = overview?.active_period ?? null;
  const recommendedPlanId = getRecommendedPlanId(plans);

  function openPlan(planId: string) {
    onNavigate(createMembershipCheckoutPath(planId));
  }

  return (
    <div className="membership-page">
      <MembershipBanner
        description={t("解锁更多 AI 能力，获得更流畅、稳定的体验")}
        onOrders={() => onNavigate(platformPaths.membershipOrders)}
        title={t("开通 OrionAI 会员")}
      />

      {paymentMessage && (
        <div className="membership-payment-return" role="status">
          <PlatformIcon name="check" size={17} />
          <span>{paymentMessage}</span>
          <button
            aria-label={t("关闭支付状态提示")}
            onClick={() => setPaymentMessage(null)}
            type="button"
          >
            <PlatformIcon name="close" size={16} />
          </button>
        </div>
      )}

      {isMembershipLoading && <MembershipLoadingState label={t("正在加载会员信息…")} />}
      {!isMembershipLoading && membershipError && !isGuest && (
        <div className="membership-load-error" role="alert">
          <span>{membershipError}</span>
          <button
            className="button button--outline"
            onClick={() => void refresh().catch(() => undefined)}
            type="button"
          >
            {t("重新加载")}
          </button>
        </div>
      )}

      <div className="membership-page__columns">
        <div className="membership-page__main-column">
          <section
            aria-labelledby="membership-plans-title"
            className="membership-plan-section"
            id="membership-plans"
          >
            <div className="membership-section-heading">
              <div>
                <h2 id="membership-plans-title">{t("选择会员套餐")}</h2>
              </div>
            </div>
            {arePlansLoading ? (
              <MembershipLoadingState label={t("正在加载套餐…")} />
            ) : plansError ? (
              <div className="membership-load-error" role="alert">
                <span>{plansError}</span>
                <button
                  className="button button--outline"
                  onClick={() => {
                    setArePlansLoading(true);
                    setPlansError(null);
                    setPlansReloadVersion((value) => value + 1);
                  }}
                  type="button"
                >
                  {t("重新加载")}
                </button>
              </div>
            ) : plans.length === 0 ? (
              <div className="membership-empty-state panel-card">{t("暂无可购买的会员套餐")}</div>
            ) : (
              <div className="membership-plan-grid">
                {plans.map((plan) => (
                  <MembershipPlanCard
                    isCurrent={activePeriod?.plan_id === plan.id}
                    isRecommended={plan.id === recommendedPlanId}
                    key={plan.id}
                    onSelect={() => openPlan(plan.id)}
                    plan={plan}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function MembershipLoadingState({ label }: { label: string }) {
  return (
    <div className="membership-loading" role="status">
      <span aria-hidden="true" className="membership-loading__spinner" />
      {label}
    </div>
  );
}
