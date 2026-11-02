import { useEffect, useState } from "react";

import { PlatformIcon } from "../platform/PlatformIcon";
import {
  createMembershipCheckoutPath,
  platformPaths,
  type PlatformRoute,
} from "../platform/platformData";
import { getMembershipOrder } from "./membershipApi";
import {
  formatDateTime,
  formatDuration,
  getOrderStatusClass,
  getOrderStatusLabel,
  getOrderTypeLabel,
} from "./membershipUtils";
import type { MembershipOrder } from "./types";
import { t } from "../../i18n/localeStore";

export function MembershipOrderDetailPage({
  onNavigate,
  orderId,
}: {
  onNavigate: (path: PlatformRoute) => void;
  orderId: string;
}) {
  const [order, setOrder] = useState<MembershipOrder | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void getMembershipOrder(orderId, controller.signal)
      .then(setOrder)
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : t("订单详情暂时无法加载。"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [orderId, reloadVersion]);

  return (
    <div className="membership-order-detail-page">
      <button
        className="membership-back-button"
        onClick={() => onNavigate(platformPaths.membershipOrders)}
        type="button"
      >
        <PlatformIcon name="arrow" size={16} />
        {t("返回订单列表")}
      </button>
      <h1 className="membership-page-title">{t("订单详情")}</h1>
      {isLoading ? (
        <div className="panel-card membership-loading" role="status">
          <span aria-hidden="true" className="membership-loading__spinner" />
          {t("正在加载订单…")}
        </div>
      ) : error ? (
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
            {t("重新加载")}
          </button>
        </div>
      ) : order ? (
        <section className="panel-card membership-order-detail">
          <div className="membership-order-detail__status">
            <span
              className={
                "membership-order-status membership-order-status--" +
                getOrderStatusClass(order.status)
              }
            >
              {getOrderStatusLabel(order.status, order.order_type)}
            </span>
          </div>
          <dl className="membership-order-detail__grid">
            <div>
              <dt>{t("订单类型")}</dt>
              <dd>{getOrderTypeLabel(order.order_type)}</dd>
            </div>
            <div>
              <dt>{t("订单编号")}</dt>
              <dd>{order.order_id}</dd>
            </div>
            <div>
              <dt>{t("套餐名称")}</dt>
              <dd>{order.plan_name}</dd>
            </div>
            <div>
              <dt>{t("购买时长")}</dt>
              <dd>{formatDuration(order.duration_days)}</dd>
            </div>
            <div>
              <dt>{t("支付金额")}</dt>
              <dd>{order.order_type === "manual_grant" ? t("免费赠送") : "¥" + order.amount}</dd>
            </div>
            <div>
              <dt>{t("创建时间")}</dt>
              <dd>{formatDateTime(order.created_at)}</dd>
            </div>
            {order.order_type === "purchase" && (
              <div>
                <dt>{t("支付时间")}</dt>
                <dd>{formatDateTime(order.paid_at)}</dd>
              </div>
            )}
          </dl>
          <div className="membership-order-detail__actions">
            {order.status === "pending" && (
              <button
                className="button button--primary"
                onClick={() =>
                  onNavigate(createMembershipCheckoutPath(order.plan_id, order.order_id))
                }
                type="button"
              >
                {t("继续支付")}
              </button>
            )}
            {(order.status === "failed" || order.status === "expired") && (
              <button
                className="button button--primary"
                onClick={() =>
                  onNavigate(createMembershipCheckoutPath(order.plan_id, order.order_id))
                }
                type="button"
              >
                {t("重新购买")}
              </button>
            )}
            <button
              className="button button--outline"
              onClick={() => onNavigate(platformPaths.membership)}
              type="button"
            >
              {t("返回会员中心")}
            </button>
          </div>
        </section>
      ) : (
        <div className="panel-card membership-empty-state">{t("未找到该订单")}</div>
      )}
    </div>
  );
}
