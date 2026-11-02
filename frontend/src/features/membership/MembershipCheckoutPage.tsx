import { useEffect, useRef, useState } from "react";

import { useToast } from "../../components/ToastProvider";
import { PlatformIcon } from "../platform/PlatformIcon";
import { platformPaths, type PlatformRoute } from "../platform/platformData";
import { PaymentMethodSelector } from "./components/PaymentMethodSelector";
import { useMembershipStatus } from "./MembershipStatusContext";
import {
  createCheckoutSession,
  createMembershipOrder,
  getMembershipOrder,
  listMembershipPlans,
  listPaymentMethods,
} from "./membershipApi";
import { formatDuration } from "./membershipUtils";
import type { MembershipOrder, MembershipPlan, PaymentMethod } from "./types";

interface MembershipCheckoutPageProps {
  isGuest: boolean;
  onNavigate: (path: PlatformRoute) => void;
  orderId: string | null;
  planId: string;
}

export function MembershipCheckoutPage({
  isGuest,
  onNavigate,
  orderId,
  planId,
}: MembershipCheckoutPageProps) {
  const { refresh } = useMembershipStatus();
  const { showToast } = useToast();
  const [plans, setPlans] = useState<MembershipPlan[]>([]);
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [currentOrder, setCurrentOrder] = useState<MembershipOrder | null>(null);
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paymentMessage, setPaymentMessage] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("payment") === "cancelled"
      ? "你已返回支付确认页，尚未确认付款。可以重新发起支付。"
      : null,
  );
  const [reloadVersion, setReloadVersion] = useState(0);
  const requestIdRef = useRef<string | null>(null);
  const submittingRef = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    const requests: [Promise<MembershipPlan[]>, Promise<PaymentMethod[]>] = [
      listMembershipPlans(controller.signal),
      isGuest ? Promise.resolve([]) : listPaymentMethods(controller.signal),
    ];

    void Promise.all(requests)
      .then(async ([availablePlans, availableMethods]) => {
        if (controller.signal.aborted) return;
        setPlans(availablePlans);
        setPaymentMethods(availableMethods);
        setSelectedMethod((current) =>
          current && availableMethods.some((method) => method.code === current)
            ? current
            : (availableMethods[0]?.code ?? null),
        );
        if (orderId && !isGuest) {
          const order = await getMembershipOrder(orderId, controller.signal);
          if (controller.signal.aborted) return;
          setCurrentOrder(order);
        } else {
          setCurrentOrder(null);
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "支付信息暂时无法加载。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [isGuest, orderId, planId, reloadVersion]);

  useEffect(() => {
    const paymentState = new URLSearchParams(window.location.search).get("payment");
    if (paymentState === "cancelled") {
      showToast("info", "支付未完成，订单状态仍以服务端查询结果为准。");
    }
  }, [showToast]);

  const plan = plans.find((item) => item.id === planId) ?? null;
  const orderMismatch = Boolean(currentOrder && currentOrder.plan_id !== planId);
  const amount = currentOrder?.amount ?? plan?.price ?? null;
  const canUseExistingOrder = currentOrder?.status === "pending";

  async function handlePayment() {
    if (submittingRef.current || !plan || !selectedMethod || isGuest || orderMismatch) return;
    submittingRef.current = true;
    setIsSubmitting(true);
    setError(null);
    setPaymentMessage(null);

    try {
      let order = canUseExistingOrder ? currentOrder : null;
      if (!order) {
        if (currentOrder?.status === "paid") {
          await refresh().catch(() => null);
          showToast("success", "该订单已支付，会员信息已刷新。");
          onNavigate(platformPaths.membership);
          return;
        }

        if (!requestIdRef.current) requestIdRef.current = window.crypto.randomUUID();
        const created = await createMembershipOrder(plan.id, requestIdRef.current);
        requestIdRef.current = null;
        order = {
          order_id: created.order_id,
          plan_id: plan.id,
          plan_name: plan.name,
          amount: created.amount,
          duration_days: created.duration_days,
          status: created.status,
          created_at: created.created_at,
          paid_at: null,
        };
        setCurrentOrder(order);
        if (order.status === "paid") {
          await refresh().catch(() => null);
          showToast("success", "该订单已支付，会员信息已刷新。");
          onNavigate(platformPaths.membership);
          return;
        }
        if (order.status !== "pending") {
          setPaymentMessage("该订单当前无法继续支付，请重新选择套餐。");
          return;
        }
      }

      const session = await createCheckoutSession(order.order_id, selectedMethod);
      const checkoutUrl = new URL(session.checkout_url);
      if (checkoutUrl.protocol !== "https:") {
        throw new Error("支付服务返回了无效的安全地址，请稍后重试。");
      }
      window.location.assign(checkoutUrl.toString());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "支付请求失败，请稍后重试。");
    } finally {
      submittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  function retryPayment() {
    if (currentOrder?.status === "failed" || currentOrder?.status === "expired") {
      setCurrentOrder(null);
    }
    void handlePayment();
  }

  const orderStatusBlocksPayment = currentOrder?.status === "paid";
  const isTerminalOrder = currentOrder?.status === "failed" || currentOrder?.status === "expired";

  return (
    <div className="membership-checkout-page">
      <button
        className="membership-back-button"
        onClick={() => onNavigate(platformPaths.membership)}
        type="button"
      >
        <PlatformIcon name="arrow" size={16} />
        返回会员中心
      </button>
      <h1 className="membership-page-title">确认支付</h1>

      {isLoading ? (
        <div className="panel-card membership-loading" role="status">
          <span aria-hidden="true" className="membership-loading__spinner" />
          正在加载套餐与支付方式…
        </div>
      ) : error && !plan ? (
        <div className="membership-load-error" role="alert">
          <span>{error}</span>
          <button
            className="button button--outline"
            onClick={() => {
              setIsLoading(true);
              setError(null);
              setReloadVersion((value) => value + 1);
            }}
            type="button"
          >
            重新加载
          </button>
        </div>
      ) : !plan ? (
        <div className="panel-card membership-empty-state" role="status">
          该套餐当前不可用，请返回会员中心重新选择。
        </div>
      ) : (
        <section className="membership-checkout-card panel-card">
          <div className="membership-checkout-summary">
            <h2>套餐信息</h2>
            {orderMismatch && (
              <p className="membership-inline-message" role="alert">
                订单与当前选择的套餐不匹配，请返回套餐列表重新选择。
              </p>
            )}
            <dl>
              <div>
                <dt>购买项目</dt>
                <dd>OrionAI 会员 · {plan.name}</dd>
              </div>
              <div>
                <dt>购买时长</dt>
                <dd>{formatDuration(currentOrder?.duration_days ?? plan.duration_days)}</dd>
              </div>
              <div>
                <dt>订单金额</dt>
                <dd className="membership-checkout-amount">{amount ? "¥" + amount : "—"}</dd>
              </div>
            </dl>
            <p className="membership-checkout-hint">
              若当前会员尚未到期，本次购买期限将在现有会员期限后顺延。预计生效日期以服务端订单和会员记录为准。
            </p>
          </div>

          <div className="membership-checkout-payment">
            <PaymentMethodSelector
              methods={paymentMethods}
              onSelect={setSelectedMethod}
              selectedCode={selectedMethod}
            />
            {isGuest && (
              <p className="membership-inline-message" role="status">
                访客账号不能购买会员，请注册或登录后继续。
              </p>
            )}
            {currentOrder && currentOrder.status !== "pending" && (
              <p className="membership-inline-message" role="status">
                当前订单状态：
                {currentOrder.status === "paid"
                  ? "已支付"
                  : currentOrder.status === "failed"
                    ? "支付失败"
                    : "已过期"}
              </p>
            )}
            {paymentMessage && (
              <p className="membership-inline-message" role="status">
                {paymentMessage}
              </p>
            )}
            {error && (
              <p
                className="membership-inline-message membership-inline-message--error"
                role="alert"
              >
                {error}
              </p>
            )}
            <div className="membership-checkout-actions">
              <button
                className="button button--outline"
                onClick={() => onNavigate(platformPaths.membership)}
                type="button"
              >
                返回
              </button>
              <button
                className="button button--primary"
                disabled={
                  isSubmitting ||
                  isGuest ||
                  paymentMethods.length === 0 ||
                  !selectedMethod ||
                  orderMismatch ||
                  orderStatusBlocksPayment
                }
                onClick={isTerminalOrder ? retryPayment : () => void handlePayment()}
                type="button"
              >
                {isSubmitting
                  ? "正在创建支付…"
                  : isTerminalOrder
                    ? "重新发起支付"
                    : "立即支付 " + (amount ? "¥" + amount : "")}
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
