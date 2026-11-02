import { useEffect, useState } from "react";

import { PlatformIcon } from "../platform/PlatformIcon";
import {
  createMembershipOrderDetailPath,
  platformPaths,
  type PlatformRoute,
} from "../platform/platformData";
import { MembershipOrderList } from "./components/MembershipOrderList";
import { listMembershipOrders } from "./membershipApi";
import type { MembershipOrder } from "./types";

const ORDERS_PAGE_SIZE = 10;

export function MembershipOrdersPage({
  onNavigate,
}: {
  onNavigate: (path: PlatformRoute) => void;
}) {
  const [orders, setOrders] = useState<MembershipOrder[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const pageCount = Math.max(1, Math.ceil(total / ORDERS_PAGE_SIZE));

  useEffect(() => {
    const controller = new AbortController();
    void listMembershipOrders(page, ORDERS_PAGE_SIZE, controller.signal)
      .then((response) => {
        setOrders(response.items);
        setTotal(response.total);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "订单记录暂时无法加载。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [page, reloadVersion]);

  return (
    <div className="membership-orders-page">
      <button
        className="membership-back-button"
        onClick={() => onNavigate(platformPaths.membership)}
        type="button"
      >
        <PlatformIcon name="arrow" size={16} />
        返回会员中心
      </button>
      <div className="membership-section-heading">
        <div>
          <h1 className="membership-page-title">我的订单</h1>
          <p>会员订单与支付状态均以服务端记录为准</p>
        </div>
        <span className="membership-orders-total">共 {total} 笔</span>
      </div>

      {isLoading ? (
        <div className="panel-card membership-loading" role="status">
          <span aria-hidden="true" className="membership-loading__spinner" />
          正在加载订单…
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
            重新加载
          </button>
        </div>
      ) : (
        <div className="panel-card membership-orders-page__list">
          <MembershipOrderList
            onOpenOrder={(orderId) => onNavigate(createMembershipOrderDetailPath(orderId))}
            orders={orders}
            showViewAll={false}
          />
          {total > 0 && (
            <nav aria-label="订单分页" className="membership-order-pagination">
              <button
                aria-label="上一页"
                className="button button--outline"
                disabled={page <= 1}
                onClick={() => {
                  setIsLoading(true);
                  setError(null);
                  setPage((value) => Math.max(1, value - 1));
                }}
                type="button"
              >
                上一页
              </button>
              <span>
                {page} / {pageCount}
              </span>
              <button
                aria-label="下一页"
                className="button button--outline"
                disabled={page >= pageCount}
                onClick={() => {
                  setIsLoading(true);
                  setError(null);
                  setPage((value) => Math.min(pageCount, value + 1));
                }}
                type="button"
              >
                下一页
              </button>
            </nav>
          )}
        </div>
      )}
    </div>
  );
}
