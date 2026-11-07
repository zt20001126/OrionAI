import { useEffect, useState } from "react";

import { PlatformIcon } from "../platform/PlatformIcon";
import {
  createMembershipCheckoutPath,
  createMembershipOrderDetailPath,
  platformPaths,
  type PlatformRoute,
} from "../platform/platformData";
import { listMembershipOrders } from "./membershipApi";
import {
  formatDateTime,
  formatDuration,
  getOrderStatusClass,
  getOrderStatusLabel,
} from "./membershipUtils";
import type { MembershipOrder, MembershipOrderStatus } from "./types";
import { t } from "../../i18n/localeStore";
import "./membership.css";

const FILTERS: Array<{ label: string; status?: MembershipOrderStatus }> = [
  { label: "全部订单" },
  { label: "待支付", status: "pending" },
  { label: "已支付", status: "paid" },
  { label: "已过期", status: "expired" },
];

/** 展示本人订单并通过服务端状态筛选和分页；调用方：应用路由。 */
export function MembershipOrdersPage({
  onNavigate,
}: {
  onNavigate: (path: PlatformRoute) => void;
}) {
  const [orders, setOrders] = useState<MembershipOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [status, setStatus] = useState<MembershipOrderStatus | undefined>();
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    const controller = new AbortController();
    void listMembershipOrders(page, pageSize, controller.signal, status)
      .then((response) => {
        setOrders(response.items);
        setTotal(response.total);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : t("订单记录暂时无法加载。"));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [page, pageSize, status, reloadVersion]);

  function reload() {
    setIsLoading(true);
    setError(null);
    setReloadVersion((version) => version + 1);
  }

  return (
    <div className="membership-orders-page">
      <button
        className="membership-back-button"
        onClick={() => onNavigate(platformPaths.membership)}
        type="button"
      >
        <PlatformIcon name="arrow" size={16} />
        {t("返回充值")}
      </button>
      <section className="membership-orders-shell">
        <header className="membership-orders-heading">
          <span className="membership-orders-heading__icon">
            <PlatformIcon name="document" size={24} />
          </span>
          <div>
            <h1 className="membership-page-title">{t("我的订单")}</h1>
            <p>{t("查看会员购买与续订记录")}</p>
          </div>
        </header>
        <div className="membership-orders-toolbar">
          <div aria-label={t("订单状态筛选")} className="membership-order-filters" role="group">
            {FILTERS.map((filter) => (
              <button
                aria-pressed={status === filter.status}
                className={status === filter.status ? "is-active" : ""}
                key={filter.label}
                onClick={() => {
                  setStatus(filter.status);
                  setPage(1);
                  setIsLoading(true);
                  setError(null);
                }}
                type="button"
              >
                {t(filter.label)}
              </button>
            ))}
          </div>
          <span className="membership-orders-total">
            {t("共")} {total} {t("笔订单")}
          </span>
        </div>
        {isLoading ? (
          <div className="membership-loading" role="status">
            <span aria-hidden="true" className="membership-loading__spinner" />
            {t("正在加载订单…")}
          </div>
        ) : error ? (
          <div className="membership-load-error" role="alert">
            <span>{error}</span>
            <button className="button button--outline" onClick={reload} type="button">
              {t("重新加载")}
            </button>
          </div>
        ) : orders.length === 0 ? (
          <div className="membership-orders-empty">
            <PlatformIcon name="document" size={30} />
            <p>{t("暂无订单记录")}</p>
            <button
              className="button button--primary"
              onClick={() => onNavigate(platformPaths.membership)}
              type="button"
            >
              {t("前往开通会员")}
            </button>
          </div>
        ) : (
          <ul className="membership-orders-table">
            {orders.map((order) => (
              <li className="membership-orders-row" key={order.order_id}>
                <span className="membership-orders-plan-icon">
                  <PlatformIcon name="crown" size={22} />
                </span>
                <div className="membership-orders-plan">
                  <strong>{order.plan_name}</strong>
                  <span>{formatDuration(order.duration_days)}</span>
                </div>
                <div className="membership-orders-meta">
                  <span>
                    {t("订单号")}　{order.order_id}
                  </span>
                  <span>
                    {t("下单时间")}　{formatDateTime(order.created_at)}
                  </span>
                </div>
                <strong className="membership-orders-amount">
                  {order.order_type === "manual_grant" ? t("免费赠送") : `¥${order.amount}`}
                </strong>
                <span
                  className={`membership-order-status membership-order-status--${getOrderStatusClass(order.status)}`}
                >
                  {getOrderStatusLabel(order.status, order.order_type)}
                </span>
                <button
                  className="button button--outline membership-orders-action"
                  onClick={() =>
                    onNavigate(
                      order.status === "pending"
                        ? createMembershipCheckoutPath(order.plan_id, order.order_id)
                        : createMembershipOrderDetailPath(order.order_id),
                    )
                  }
                  type="button"
                >
                  {order.status === "pending" ? t("立即支付") : t("查看详情")}
                </button>
              </li>
            ))}
          </ul>
        )}
        <footer className="membership-order-pagination">
          <label>
            {t("每页")}
            <select
              aria-label={t("每页条数")}
              onChange={(event) => {
                setPageSize(Number(event.target.value));
                setPage(1);
                setIsLoading(true);
              }}
              value={pageSize}
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
            {t("条")}
          </label>
          <div>
            <button
              aria-label={t("上一页")}
              className="button button--outline"
              disabled={page <= 1 || isLoading}
              onClick={() => {
                setPage((current) => current - 1);
                setIsLoading(true);
              }}
              type="button"
            >
              <PlatformIcon name="arrow" size={16} />
            </button>
            <span className="membership-order-page-number">{page}</span>
            <button
              aria-label={t("下一页")}
              className="button button--outline"
              disabled={page >= pageCount || isLoading}
              onClick={() => {
                setPage((current) => current + 1);
                setIsLoading(true);
              }}
              type="button"
            >
              <PlatformIcon name="arrow" size={16} />
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
