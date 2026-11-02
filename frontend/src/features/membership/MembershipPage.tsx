import { useEffect, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { PlatformIcon } from "../platform/PlatformIcon";
import {
  createMembershipCheckoutPath,
  createMembershipOrderDetailPath,
  platformPaths,
  type PlatformRoute,
} from "../platform/platformData";
import { MembershipBanner } from "./components/MembershipBanner";
import { MembershipInfo } from "./components/MembershipInfo";
import { MembershipOrderList } from "./components/MembershipOrderList";
import { MembershipPlanCard } from "./components/MembershipPlanCard";
import { useMembershipStatus } from "./MembershipStatusContext";
import { getMembershipOrder, listMembershipOrders, listMembershipPlans } from "./membershipApi";
import { formatDate, getRecommendedPlanId } from "./membershipUtils";
import type { MembershipOrder, MembershipPlan } from "./types";

import "./membership.css";
import { t } from "../../i18n/localeStore";

const RECENT_ORDERS_SIZE = 5;
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
  const [orders, setOrders] = useState<MembershipOrder[]>([]);
  const [areOrdersLoading, setAreOrdersLoading] = useState(!isGuest);
  const [ordersError, setOrdersError] = useState<string | null>(null);
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
    if (isGuest) {
      return;
    }

    const controller = new AbortController();
    void listMembershipOrders(1, RECENT_ORDERS_SIZE, controller.signal)
      .then((response) => {
        setOrders(response.items);
        setOrdersError(null);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setOrdersError(cause instanceof Error ? cause.message : t("订单记录暂时无法加载。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setAreOrdersLoading(false);
      });
    return () => controller.abort();
  }, [isGuest]);

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

  const reportedActive = overview?.active_period ?? null;
  const activePeriod = reportedActive;
  const expiredPeriod = overview?.latest_expired_period ?? null;
  const upcomingPeriods = overview?.upcoming_periods ?? [];
  const recommendedPlanId = getRecommendedPlanId(plans);

  function openPlan(planId: string) {
    onNavigate(createMembershipCheckoutPath(planId));
  }

  return (
    <div className="membership-page">
      <MembershipBanner
        description={t(
          activePeriod
            ? "会员状态正常，后续购买将从现有有效期结束后顺延。"
            : expiredPeriod
              ? "会员已过期，历史订单和会员记录仍会保留。"
              : upcomingPeriods.length > 0
                ? "会员期限已排期，后续期限会按顺序生效。"
                : "解锁更流畅、更稳定的 AI 体验",
        )}
        state={activePeriod ? "active" : expiredPeriod ? "expired" : undefined}
        title={
          activePeriod
            ? t("OrionAI 会员")
            : expiredPeriod
              ? t("会员已过期")
              : upcomingPeriods.length > 0
                ? t("会员期限已排期")
                : t("开通 OrionAI 会员")
        }
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

      {activePeriod && (
        <MembershipInfo
          period={activePeriod}
          onRenew={() => onNavigate(createMembershipCheckoutPath(activePeriod.plan_id))}
        />
      )}

      {!activePeriod && expiredPeriod && (
        <section className="membership-expired-card panel-card">
          <div>
            <h2>{t("最近一次会员记录")}</h2>
            <p>{t("到期时间：")}{formatDate(expiredPeriod.expires_at)}</p>
          </div>
          <button
            className="button button--primary"
            onClick={() =>
              document.getElementById("membership-plans")?.scrollIntoView({ behavior: "smooth" })
            }
            type="button"
          >
            {t("重新开通")}
          </button>
        </section>
      )}

      {upcomingPeriods.length > 0 && (
        <section className="membership-upcoming panel-card">
          <h2>{t("已排期的会员期限")}</h2>
          <ul>
            {upcomingPeriods.map((period) => (
              <li key={period.order_id}>
                <span>{period.plan_name}</span>
                <span>
                  {formatDate(period.starts_at)} {t("起 · 至")} {formatDate(period.expires_at)}
                </span>
              </li>
            ))}
          </ul>
        </section>
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
                <p>{t("所有套餐享受相同会员身份，仅有效期不同")}</p>
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

          <section aria-labelledby="membership-note-title" className="membership-note panel-card">
            <h2 id="membership-note-title">{t("会员说明")}</h2>
            <ul>
              <li>{t("所有会员套餐享受相同的会员身份。")}</li>
              <li>{t("不同套餐仅有效期不同。")}</li>
              <li>{t("可以在会员到期前继续购买，新增期限会在现有期限后顺延。")}</li>
            </ul>
          </section>
        </div>

        <aside className="membership-page__side-column">
          {isGuest ? (
            <section className="panel-card membership-guest-note">
              <h2>{t("登录后查看订单")}</h2>
              <p>{t("访客可以浏览套餐，注册或登录后即可购买并查看会员记录。")}</p>
            </section>
          ) : (
            <>
              {areOrdersLoading ? (
                <section className="panel-card">
                  <MembershipLoadingState label={t("正在加载订单…")} />
                </section>
              ) : ordersError ? (
                <section className="panel-card membership-orders-error" role="alert">
                  <h2>{t("订单记录暂不可用")}</h2>
                  <p>{ordersError}</p>
                  <button
                    className="button button--outline"
                    onClick={() => onNavigate(platformPaths.membershipOrders)}
                    type="button"
                  >
                    {t("前往订单页重试")}
                  </button>
                </section>
              ) : (
                <MembershipOrderList
                  onOpenOrder={(orderId) => onNavigate(createMembershipOrderDetailPath(orderId))}
                  onViewAll={() => onNavigate(platformPaths.membershipOrders)}
                  orders={orders}
                />
              )}
            </>
          )}
        </aside>
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
